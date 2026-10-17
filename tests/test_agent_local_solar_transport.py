import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch
sys.modules.setdefault('websocket',types.ModuleType('websocket'))
spec=importlib.util.spec_from_file_location('agent_local_solar_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class TransportTests(unittest.TestCase):
 def test_native_activation_never_runs_as_durable_heartbeat_job(self):
  with patch.object(agent,'relay_command') as dispatch:
   result=agent.queued_command_result('token',{'action':'commissioning.activate_ddzy422','payload':{'operation':'activate','confirmed':True}})
  self.assertFalse(result['ok']);dispatch.assert_not_called()
 def test_native_activation_dispatch_passes_readiness_and_explicit_payload(self):
  connector=types.ModuleType('ddzy422_activation');connector.activate=Mock(return_value={'status':'activation_pending'})
  payload={'operation':'activate','confirmed':True,'ownerScope':'a'*64};manifest={'domain':'labox_ddzy422','version':'0.1.1','is_built_in':False}
  with patch.dict(sys.modules,{'ddzy422_activation':connector}),patch.object(agent,'home_assistant_ws_command',return_value=manifest):
   result=agent.relay_command('token',{'action':'commissioning.activate_ddzy422','payload':payload})
  self.assertTrue(result['ok']);self.assertEqual(connector.activate.call_args.args[0],payload);self.assertEqual(connector.activate.call_args.kwargs['loaded_manifest'],manifest)
 def test_install_dispatch_does_not_restart_ha(self):
  connector=types.ModuleType('ddzy422_setup');connector.install=Mock(return_value={'restartRequired':True});connector.verify_bundle=Mock(return_value={'version':'0.1.1'})
  with patch.dict(sys.modules,{'ddzy422_setup':connector}),patch.object(agent,'request_json') as ha:
   result=agent.relay_command('token',{'action':'commissioning.install_ddzy422'})
  self.assertTrue(result['ok']);self.assertTrue(result['result']['restartRequired']);ha.assert_not_called()
 def test_configure_dispatch_uses_box_native_network_and_requested_identity(self):
  for action,name in [('commissioning.configure_ddzy422','ddzy422_setup'),('commissioning.configure_deye_micro','micro_setup')]:
   connector=types.ModuleType(name);connector.configure=Mock(return_value={'entryId':'local'})
   payload={'host':'192.168.6.194','loggerSerial':2616442643,'mac':'D42787012CD2'};adapters=[{'enabled':True}]
   with patch.dict(sys.modules,{name:connector}),patch.object(agent,'home_assistant_ws_command',return_value={'adapters':adapters}):
    result=agent.relay_command('token',{'action':action,'payload':payload})
   self.assertTrue(result['ok']);self.assertEqual(connector.configure.call_args.args[:2],(payload,adapters))

 def test_new_solar_measurements_invalidate_identity_cache_only_after_success(self):
  connector=types.ModuleType('solar_setup');connector.configure=Mock(return_value={'entryId':'same-entry'})
  agent.REGISTRY_METADATA_FETCHED_AT=12345
  with patch.dict(sys.modules,{'solar_setup':connector}),patch.object(agent,'home_assistant_ws_command',return_value={'adapters':[]}):
   result=agent.relay_command('token',{'action':'commissioning.configure_deye','payload':{}})
   self.assertTrue(result['ok']);self.assertEqual(agent.REGISTRY_METADATA_FETCHED_AT,0)
   agent.REGISTRY_METADATA_FETCHED_AT=999;connector.configure.side_effect=RuntimeError('not ready')
   result=agent.relay_command('token',{'action':'commissioning.configure_deye','payload':{}})
   self.assertFalse(result['ok']);self.assertEqual(agent.REGISTRY_METADATA_FETCHED_AT,999)

if __name__=='__main__':unittest.main()
