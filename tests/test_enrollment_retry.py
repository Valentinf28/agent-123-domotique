import importlib.util
from pathlib import Path
import sys,types,tempfile,json,unittest
from unittest.mock import patch
if 'websocket' not in sys.modules:sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('agent_enrollment_retry',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class EnrollmentRetryTests(unittest.TestCase):
 def test_lost_response_and_restart_reuses_persisted_secret(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(agent,'STATE_PATH',Path(directory)/'state.json'):
   calls=[]
   def request(url,**kwargs):
    saved=json.loads(agent.STATE_PATH.read_text());token=kwargs['payload']['enrollmentToken']
    self.assertEqual(saved['pending_enrollment']['token'],token)
    calls.append(token)
    if len(calls)==1:raise TimeoutError('lost response')
    return {'agentId':'same-box','token':token}
   with patch.object(agent,'request_json',side_effect=request):
    with self.assertRaises(TimeoutError):agent.enroll('https://portal.test/api','ABCD2345')
    state=agent.enroll('https://portal.test/api','ABCD2345')
   self.assertEqual(calls[0],calls[1]);self.assertEqual(len(calls[0]),64)
   self.assertEqual(state,{'agent_id':'same-box','token':calls[0]})
   self.assertEqual(json.loads(agent.STATE_PATH.read_text()),state)
   self.assertEqual(agent.STATE_PATH.stat().st_mode&0o777,0o600)
 def test_existing_identity_is_never_replaced(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(agent,'STATE_PATH',Path(directory)/'state.json'),patch.object(agent,'request_json') as request:
   state={'token':'existing-secret','agent_id':'existing-box'};agent.write_state(state)
   self.assertEqual(agent.enroll('https://another.test','NEWC2345'),state);request.assert_not_called()
 def test_failure_to_persist_prevents_enrollment(self):
  with patch.object(agent,'read_json',return_value={}),patch.object(agent,'write_state',side_effect=OSError()),patch.object(agent,'request_json') as request:
   with self.assertRaises(OSError):agent.enroll('https://portal.test','ABCD2345')
   request.assert_not_called()
