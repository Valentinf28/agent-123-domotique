import importlib.util
from pathlib import Path
import socket
import sys
import threading
import types
import unittest

if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
spec = importlib.util.spec_from_file_location("agent_tunnel_test", Path(__file__).parents[1] / "agent_123_domotique/agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class WaitingReader:
    """Real blocking socket with the same competing reader lock as websocket-client."""
    def __init__(self):
        self.socket, self.peer = socket.socketpair()
        self.lock = threading.Lock()
        self.reading = threading.Event()
        self.close_called = False

    def read(self):
        with self.lock:
            self.reading.set()
            try:
                self.socket.recv(1)
            except OSError:
                pass

    def close(self):
        self.close_called = True
        with self.lock:
            self.socket.close()

    def abort(self):
        self.socket.shutdown(socket.SHUT_RDWR)

    def shutdown(self):
        self.socket.close()


class TunnelCloseTests(unittest.TestCase):
    def test_close_interrupts_blocked_reader_without_stalling_commands(self):
        upstream = WaitingReader()
        reader = threading.Thread(target=upstream.read, daemon=True)
        reader.start()
        self.assertTrue(upstream.reading.wait(1))
        agent.HA_TUNNELS["test"] = upstream
        results = []
        closer = threading.Thread(target=lambda: results.append(agent.relay_command("unused", {
            "id": "close", "action": "ha.ws.close", "payload": {"tunnelId": "test"},
        })), daemon=True)
        try:
            closer.start()
            closer.join(1)
            self.assertFalse(closer.is_alive(), "A tunnel close must not block subsequent relay commands")
            reader.join(1)
            self.assertFalse(reader.is_alive())
            self.assertTrue(results[0]["ok"])
            self.assertFalse(upstream.close_called)
            self.assertNotIn("test", agent.HA_TUNNELS)
            self.assertTrue(agent.relay_command("unused", {"id": "again", "action": "ha.ws.close", "payload": {"tunnelId": "test"}})["ok"])
        finally:
            upstream.peer.close()
            agent.close_ha_tunnel(upstream)
            reader.join(1)
            closer.join(1)
