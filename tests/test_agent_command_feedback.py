import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import urllib.error
if 'websocket' not in sys.modules:
    sys.modules['websocket'] = types.ModuleType('websocket')
spec = importlib.util.spec_from_file_location('feedback_agent', Path(__file__).parents[1] / 'agent_123_domotique/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class CommandFeedbackTests(unittest.TestCase):
    def run_cycles(self, fail_confirmation=False):
        state={'token':'saved-identity','agent_id':'own-box'}
        sent=[];saved=[];sleeps=[]
        command={'id':'command-fixture','action':'ha.services.call','payload':{'domain':'switch','service':'turn_off','data':{'entity_id':'switch.fixture'}}}
        def heartbeat(_url,_token,summary):
            sent.append(copy.deepcopy(summary))
            if len(sent)==1:return {'commands':[command]}
            if fail_confirmation and len(sent)==2:raise urllib.error.URLError('network unavailable')
            return {}
        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps)==(3 if fail_confirmation else 2):raise KeyboardInterrupt
        with ExitStack() as stack:
            stack.enter_context(patch.dict(agent.os.environ,{'SUPERVISOR_TOKEN':'fixture'}))
            stack.enter_context(patch.object(agent,'read_json',return_value={'portal_url':'https://portal.example/api'}))
            stack.enter_context(patch.object(agent,'restore_identity',return_value=state))
            stack.enter_context(patch.object(agent,'publish_local_configuration'))
            stack.enter_context(patch.object(agent,'home_assistant_summary',side_effect=lambda *_a,**_k:{'haVersion':'test','inventoryCount':1,'inventory':[{'entityId':'switch.fixture','state':'on' if not sent else 'off'}]}))
            stack.enter_context(patch.object(agent,'heartbeat',side_effect=heartbeat))
            execute=stack.enter_context(patch.object(agent,'queued_command_result',return_value={'ok':True}))
            stack.enter_context(patch.object(agent,'fetch_relay_configuration',side_effect=RuntimeError('unused')))
            stack.enter_context(patch.object(agent.threading,'Thread'))
            stack.enter_context(patch.object(agent,'write_state',side_effect=lambda value:saved.append(copy.deepcopy(value))))
            stack.enter_context(patch.object(agent.time,'monotonic',return_value=100))
            stack.enter_context(patch.object(agent.time,'sleep',side_effect=sleep))
            with self.assertRaises(KeyboardInterrupt):agent.main()
        execute.assert_called_once_with('fixture',command)
        self.assertEqual(sent[1]['inventory'][0]['state'],'off')
        self.assertEqual(sent[1]['commandResults'],[{'id':'command-fixture','ok':True,'error':''}])
        self.assertEqual(saved[0]['command_results'],sent[1]['commandResults'])
        self.assertNotIn('command_results',state)
        return sent,sleeps
    def test_confirmation_and_fresh_state_follow_execution_without_periodic_wait(self):
        _,sleeps=self.run_cycles()
        self.assertEqual(sleeps,[0.2,5])
    def test_lost_confirmation_retries_durable_result_at_normal_rate_without_replaying_command(self):
        sent,sleeps=self.run_cycles(True)
        self.assertEqual(sleeps,[0.2,5,5])
        self.assertEqual(sent[1]['commandResults'],sent[2]['commandResults'])
if __name__=='__main__':unittest.main()
