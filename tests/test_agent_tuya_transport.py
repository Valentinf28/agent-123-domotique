import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch
if 'websocket' not in sys.modules:sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('agent_tuya_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class AgentTuyaTransportTests(unittest.TestCase):
 def test_tuya_is_rejected_on_durable_command_path(self):
  with patch.object(agent,'relay_command') as live:
   result=agent.queued_command_result('supervisor',{'action':'commissioning.tuya','payload':{'userCode':'private'}})
  self.assertFalse(result['ok']);live.assert_not_called();self.assertNotIn('private',str(result))
 def test_live_flow_uses_only_native_ha_endpoint_and_registry(self):
  module=types.ModuleType('tuya_setup')
  def configure(payload,call,registry):
   call('/config/config_entries/flow',method='POST',payload={'handler':'tuya'});self.assertEqual(registry({'type':'config/entity_registry/list'}),[]);return {'connector':'tuya','status':'user_code','devicesVerified':False}
  module.configure=configure
  with patch.dict(sys.modules,{'tuya_setup':module}),patch.object(agent,'request_json') as http,patch.object(agent,'home_assistant_ws_command') as ws:
   ws.return_value={'result':[]}
   result=agent.relay_command('supervisor',{'id':'live','action':'commissioning.tuya','payload':{}})
  self.assertTrue(result['ok']);self.assertTrue(http.call_args.args[0].endswith('/config/config_entries/flow'));ws.assert_called_once_with('supervisor',{'type':'config/entity_registry/list'})
 def test_upstream_errors_never_reveal_codes_or_qr(self):
  module=types.ModuleType('tuya_setup');module.configure=Mock(side_effect=RuntimeError('UserCode private-qr-token'))
  with patch.dict(sys.modules,{'tuya_setup':module}):result=agent.relay_command('supervisor',{'id':'live','action':'commissioning.tuya','payload':{}})
  self.assertFalse(result['ok']);self.assertNotIn('private-qr-token',str(result))
if __name__=='__main__':unittest.main()
