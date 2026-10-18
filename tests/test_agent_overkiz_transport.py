import importlib.util
from pathlib import Path
import sys,types,unittest
from unittest.mock import Mock,patch
if 'websocket' not in sys.modules:sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('agent_overkiz_transport',Path(__file__).parents[1]/'agent_123_domotique/agent.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class AgentOverkizTransportTests(unittest.TestCase):
 def test_no_durable_heartbeat(self):
  with patch.object(agent,'relay_command') as live:result=agent.queued_command_result('supervisor',{'action':'commissioning.overkiz','payload':{'password':'secret'}})
  live.assert_not_called();self.assertFalse(result['ok']);self.assertNotIn('secret',str(result))
 def test_native_exception_is_sanitized(self):
  module=types.ModuleType('overkiz_setup');module.configure=Mock(side_effect=RuntimeError('secret-password secret-token account@example.test'))
  with patch.dict(sys.modules,{'overkiz_setup':module}):result=agent.relay_command('supervisor',{'id':'commissioning-test','action':'commissioning.overkiz','payload':{}})
  self.assertFalse(result['ok']);self.assertNotIn('secret',str(result));self.assertNotIn('account@',str(result))
 def test_cover_attributes_available_without_any_command(self):
  for key in ('supported_features','current_position','assumed_state','device_class'):self.assertIn(key,agent.SAFE_ATTRIBUTE_KEYS)
if __name__=='__main__':unittest.main()
