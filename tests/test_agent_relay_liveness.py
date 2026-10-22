from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_relay_liveness", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class RelayTimeout(Exception):
    pass


class FakeSocket:
    def __init__(self):
        self.responses = [
            json.dumps({"type": "authenticated"}),
            RelayTimeout(),
            RelayTimeout(),
        ]
        self.sent = []
        self.timeouts = []

    def send(self, value):
        self.sent.append(json.loads(value))

    def recv(self):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def settimeout(self, value):
        self.timeouts.append(value)


class RelayLivenessTests(unittest.TestCase):
    def test_heartbeat_wake_interrupts_wait_without_dispatching_a_device_command(self):
        socket = FakeSocket()
        socket.responses = [json.dumps({'type':'authenticated'}),json.dumps({'type':'heartbeat.wake'}),RuntimeError('stop fixture')]
        agent.HEARTBEAT_WAKE_EVENT.clear()
        with patch.object(agent.websocket,'WebSocketTimeoutException',RelayTimeout,create=True),patch.object(agent,'relay_command') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'stop fixture'):agent.relay_connected_session(socket,'house','token','supervisor')
        self.assertTrue(agent.HEARTBEAT_WAKE_EVENT.wait(0));dispatch.assert_not_called()
        self.assertEqual(len(socket.sent),1)
        agent.HEARTBEAT_WAKE_EVENT.clear()

    def test_reconnects_when_ping_receives_no_pong(self):
        socket = FakeSocket()
        previous_timeout = getattr(agent.websocket, "WebSocketTimeoutException", None)
        agent.websocket.WebSocketTimeoutException = RelayTimeout
        try:
            with self.assertRaisesRegex(RuntimeError, "ne répond plus"):
                agent.relay_connected_session(socket, "house", "token", "supervisor")
        finally:
            if previous_timeout is None:
                delattr(agent.websocket, "WebSocketTimeoutException")
            else:
                agent.websocket.WebSocketTimeoutException = previous_timeout

        self.assertEqual(socket.sent[0]["type"], "authenticate")
        self.assertEqual(socket.sent[1]["type"], "ping")
        self.assertEqual(
            socket.timeouts,
            [agent.RELAY_IDLE_TIMEOUT_SECONDS, agent.RELAY_PONG_TIMEOUT_SECONDS],
        )


if __name__ == "__main__":
    unittest.main()
