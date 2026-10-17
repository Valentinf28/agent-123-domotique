import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
if 'websocket' not in sys.modules:sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('agent_ev_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class AgentEvTransportTests(unittest.TestCase):
 def test_ev_actions_never_enter_durable_command_queue(self):
  for action in ('commissioning.ev_discover','commissioning.lektrico'):
   with patch.object(agent,'relay_command') as live:
    self.assertFalse(agent.queued_command_result('fixture',{'action':action})['ok']);live.assert_not_called()
 def test_live_actions_only_invoke_native_module_and_filter_upstream_errors(self):
  for action,module_name,function in [('commissioning.ev_discover','ev_discovery','discover'),('commissioning.lektrico','lektrico_setup','configure')]:
   module=types.ModuleType(module_name)
   def run(payload,call,registry):
    call('/config/config_entries/entry');registry({'type':'config/device_registry/list'})
    return {'connector':'ev','status':'not_configured','devicesVerified':False}
   setattr(module,function,run)
   with patch.dict(sys.modules,{module_name:module}),patch.object(agent,'request_json') as http,patch.object(agent,'home_assistant_ws_command') as ws:
    ws.return_value={'success':True,'result':[]}
    result=agent.relay_command('fixture',{'id':'fixture','action':action,'payload':{}})
   self.assertTrue(result['ok']);self.assertTrue(http.call_args.args[0].endswith('/config/config_entries/entry'))
   ws.assert_called_once_with('fixture',{'type':'config/device_registry/list'})
   def fail(*args,**kwargs):raise RuntimeError('PRIVATE_UPSTREAM')
   setattr(module,function,fail)
   with patch.dict(sys.modules,{module_name:module}):result=agent.relay_command('fixture',{'id':'fixture','action':action,'payload':{}})
   self.assertFalse(result['ok']);self.assertNotIn('PRIVATE_UPSTREAM',str(result))
if __name__=='__main__':unittest.main()
