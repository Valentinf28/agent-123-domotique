import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch
sys.modules.setdefault('websocket',types.ModuleType('websocket'))
spec=importlib.util.spec_from_file_location('agent_update_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
import installation_update as updates
class TransportTests(unittest.TestCase):
 def test_update_cannot_enter_durable_command_queue(self):
  with patch.object(agent,'relay_command') as dispatch:
   result=agent.queued_command_result('token',{'action':'installation.update','payload':{'operation':'execute'}})
  self.assertFalse(result['ok']);dispatch.assert_not_called()
 def test_management_ws_catalog_access_is_not_added(self):
  import installation_reset
  with patch.object(installation_reset,'blocks_mutations',return_value=True),patch.object(agent.websocket,'create_connection',create=True) as connection:
   for command in ({'type':'supervisor/api','endpoint':'/store','method':'get'},{'type':'supervisor/api','endpoint':'/addons/x/update','method':'post'}):
    with self.assertRaises(RuntimeError):agent.home_assistant_ws_command('token',command)
  connection.assert_not_called()
 def test_catalog_callback_uses_native_service_without_forbidden_supervisor_proxy(self):
  operation=Mock();operation.command.return_value={'state':'refreshing_catalog'}
  with patch.object(updates,'Update',return_value=operation) as factory,patch.object(agent,'request_json',return_value=[]) as request,patch.object(agent,'home_assistant_ws_command',return_value={} ) as call:
   agent.relay_command('token',{'action':'installation.update','payload':{'operation':'prepare','endpoint':'/addons/other/update'}})
   factory.call_args.kwargs['refresh_catalog']('update.agent_labo')
   call.assert_not_called()
   request.assert_called_once_with(agent.SUPERVISOR_API+'/services/homeassistant/update_entity',token='token',method='POST',payload={'entity_id':'update.agent_labo'},timeout=65)
 def test_catalog_endpoint_remains_forbidden_outside_maintenance_worker(self):
  import installation_reset
  with patch.object(installation_reset,'blocks_mutations',return_value=True),patch.object(agent.websocket,'create_connection',create=True) as connection:
   with self.assertRaises(RuntimeError):agent.home_assistant_ws_command('token',{'type':'supervisor/api','endpoint':'/store/reload','method':'post','timeout':60})
  connection.assert_not_called()
 def test_supervisor_catalog_command_stays_blocked_even_in_update_worker(self):
  import installation_reset
  with patch.object(installation_reset,'blocks_mutations',return_value=True),patch.object(agent.threading,'current_thread',return_value=types.SimpleNamespace(name='installation-update')),patch.object(agent.websocket,'create_connection',create=True) as connection:
   with self.assertRaises(RuntimeError):agent.home_assistant_ws_command('token',{'type':'supervisor/api','endpoint':'/store/reload','method':'post','timeout':60})
  connection.assert_not_called()
 def test_dispatch_binds_real_agent_version_and_native_registry(self):
  operation=Mock();operation.command.return_value={'state':'prepared'}
  with patch.object(updates,'Update',return_value=operation) as factory,patch.object(agent,'request_json'):
   result=agent.relay_command('token',{'action':'installation.update','payload':{'operation':'status','ownerScope':'a'*64}})
  self.assertTrue(result['ok']);self.assertEqual(factory.call_args.kwargs['runtime_version'],agent.AGENT_VERSION);operation.command.assert_called_once()


if __name__=='__main__':unittest.main()
