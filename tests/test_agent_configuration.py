import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
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

if __name__ == '__main__':
    unittest.main()
