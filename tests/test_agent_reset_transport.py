import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
sys.modules.setdefault('websocket',types.ModuleType('websocket'))
spec=importlib.util.spec_from_file_location('agent_reset_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
import installation_reset as reset

class ResetTransportTests(unittest.TestCase):
 def test_queued_reset_refused_before_dispatch(self):
  with patch.object(a,'relay_command') as dispatch:
   result=a.queued_command_result('token',{'action':'installation.reset','payload':{'operation':'execute'}})
  self.assertFalse(result['ok']);dispatch.assert_not_called()
 def test_reset_routes_only_to_internal_supervisor_and_closes_tunnels(self):
  handler=Mock();handler.command.return_value={'state':'backing_up'}
  tunnel=Mock();a.HA_TUNNELS['old']=tunnel
  with patch.object(reset,'Reset',return_value=handler),patch.object(reset,'blocks_mutations',return_value=False):
   result=a.relay_command('token',{'id':'123','action':'installation.reset','payload':{'operation':'status','ownerScope':'a'*64}})
  self.assertTrue(result['ok']);handler.command.assert_called_once();self.assertNotIn('old',a.HA_TUNNELS);tunnel.abort.assert_called_once()
 def test_mutating_relay_commands_never_reach_ha_during_reset(self):
  with patch.object(reset,'blocks_mutations',return_value=True),patch.object(a,'request_json') as request:
   for action in ('ha.service','commissioning.configure_deye','ha.ws.open','ha.ws.send','ha.proxy'):
    self.assertFalse(a.relay_command('token',{'action':action,'payload':{}})['ok'])
  request.assert_not_called()
 def test_background_rest_writes_blocked_but_reads_allowed(self):
  with patch.object(reset,'blocks_mutations',return_value=True),patch.object(a.urllib.request,'build_opener') as opener:
   request=opener.return_value.open
   with self.assertRaises(RuntimeError):a.request_json(a.SUPERVISOR_API+'/services/automation/reload',method='POST',payload={})
  request.assert_not_called()
 def test_only_factory_callback_can_enter_owned_cleanup(self):
  import factory_stage
  with patch.object(reset,'blocks_mutations',return_value=True),patch.object(factory_stage,'permits_cleanup_request',return_value=True),patch.object(a.urllib.request,'build_opener') as opener:
   request=opener.return_value.open
   with self.assertRaises(RuntimeError):a.request_json(a.SUPERVISOR_API+'/config/config_entries/entry/old',method='DELETE')
   request.assert_not_called()
   request.return_value.__enter__.return_value.read.return_value=b'{}'
   a.request_json(a.SUPERVISOR_API+'/config/config_entries/entry/old',method='DELETE',_factory_cleanup=True)
   request.assert_called_once()
  with patch.object(reset,'blocks_mutations',return_value=True),patch.object(factory_stage,'permits_cleanup_request',return_value=False),patch.object(a.urllib.request,'build_opener') as opener:
   request=opener.return_value.open
   with self.assertRaises(RuntimeError):a.request_json(a.SUPERVISOR_API+'/services/switch/turn_on',method='POST',_factory_cleanup=True)
   request.assert_not_called()
 def test_mutating_native_ws_never_opens_during_reset(self):
  with patch.object(reset,'blocks_mutations',return_value=True),patch.object(a.websocket,'create_connection',create=True) as request:
   with self.assertRaises(RuntimeError):a.home_assistant_ws_command('token',{'type':'config/config_entries/update'})
  request.assert_not_called()

if __name__=='__main__':unittest.main()
