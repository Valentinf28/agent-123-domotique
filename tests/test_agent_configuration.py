import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

if 'websocket' not in sys.modules:
    sys.modules['websocket'] = types.ModuleType('websocket')
spec = importlib.util.spec_from_file_location('configuration_agent', Path(__file__).parents[1] / 'agent_123_domotique/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class ConfigurationTests(unittest.TestCase):
    def fetch(self, relay):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps({'relay': relay}).encode())
        with patch.object(agent.urllib.request, 'build_opener', return_value=opener):
            result = agent.fetch_relay_configuration('https://portal.example/api', 'agent-only')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://portal.example/api/agent/configuration')
        self.assertEqual(request.get_header('Authorization'), 'Bearer agent-only')
        return result

    def test_valid_enrolled_identity(self):
        relay = {'url': 'wss://relay.example/v1/agent', 'houseId': 'new-box', 'token': 'a' * 64}
        self.assertEqual(self.fetch(relay), relay)

    def test_rejects_insecure_or_malformed_configuration(self):
        valid = {'url': 'wss://relay.example/v1/agent', 'houseId': 'new-box', 'token': 'a' * 64}
        for patch_values in ({'url': 'ws://relay.example'}, {'url': 'wss://user:pass@relay.example'}, {'houseId': '../other'}, {'token': ''}, {'token': 'x' * 64}, {'token': None}):
            with self.subTest(patch_values=patch_values), self.assertRaises(RuntimeError):
                self.fetch({**valid, **patch_values})

    def test_insecure_portal_never_receives_token(self):
        with patch.object(agent.urllib.request, 'build_opener') as opener:
            with self.assertRaises(RuntimeError):
                agent.fetch_relay_configuration('http://portal.example/api', 'secret')
            opener.assert_not_called()

    def test_stopped_relay_does_not_connect(self):
        stop = agent.threading.Event()
        stop.set()
        with patch.object(agent.websocket, 'create_connection', create=True) as connect:
            agent.relay_forever('wss://relay.example', 'house', 'token', 'supervisor', stop)
            connect.assert_not_called()

class StartupTests(unittest.TestCase):
    def run_cycle(self, configuration_error=False, explicit=False):
        options={'portal_url':'https://portal.example/api','enrollment_code':''}
        if explicit:
            options.update(relay_url='wss://existing.example',relay_house_id='existing-house',relay_token='existing-token')
        with ExitStack() as stack:
            stack.enter_context(patch.dict(agent.os.environ, {'SUPERVISOR_TOKEN':'internal-test'}))
            stack.enter_context(patch.object(agent,'read_json',side_effect=[options,{'token':'saved-identity'}]))
            enroll=stack.enter_context(patch.object(agent,'enroll'))
            stack.enter_context(patch.object(agent,'home_assistant_summary',return_value={'haVersion':'test','inventoryCount':0}))
            heartbeat=stack.enter_context(patch.object(agent,'heartbeat',return_value={}))
            fetch=stack.enter_context(patch.object(agent,'fetch_relay_configuration',return_value={'url':'wss://relay.example','houseId':'own-house','token':'a'*64}))
            if configuration_error: fetch.side_effect=RuntimeError('relay offline')
            thread=stack.enter_context(patch.object(agent.threading,'Thread'))
            stack.enter_context(patch.object(agent.time,'sleep',side_effect=KeyboardInterrupt))
            with self.assertRaises(KeyboardInterrupt):agent.main()
            enroll.assert_not_called()
            heartbeat.assert_called_once()
            if explicit:
                fetch.assert_not_called()
                self.assertEqual(thread.call_args.kwargs['args'][:3],('wss://existing.example','existing-house','existing-token'))
            elif configuration_error:
                self.assertFalse(any(call.kwargs.get("target") == agent.relay_forever for call in thread.call_args_list))
            else:
                fetch.assert_called_once_with('https://portal.example/api','saved-identity')
                self.assertEqual(sum(call.kwargs.get("target") == agent.relay_forever for call in thread.call_args_list), 1)

    def test_restart_uses_saved_identity_without_new_enrollment(self):
        self.run_cycle()

    def test_relay_failure_does_not_stop_portal_heartbeat(self):
        self.run_cycle(configuration_error=True)

    def test_existing_manual_relay_is_preserved(self):
        self.run_cycle(explicit=True)

if __name__ == '__main__':
    unittest.main()
