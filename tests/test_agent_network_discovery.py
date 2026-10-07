import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
spec = importlib.util.spec_from_file_location("agent_network_test", Path(__file__).parents[1] / "agent_123_domotique/agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class AgentDiscoveryTests(unittest.TestCase):
    def test_uses_box_interfaces_not_remote_targets(self):
        module = types.ModuleType("network_discovery")
        module.discover_solarman = Mock(return_value={"devices": [], "scope": "solar_loggers"})
        adapters = [{"enabled": True, "ipv4": [{"address": "192.168.6.179", "network_prefix": 24}]}]
        with patch.dict(sys.modules, {"network_discovery": module}), patch.object(agent, "home_assistant_ws_command", return_value={"adapters": adapters}) as network:
            result = agent.relay_command("internal-token", {
                "id": "scan", "action": "commissioning.discover_solar",
                "payload": {"host": "8.8.8.8", "adapters": [{"address": "8.8.8.8"}]},
            })
        network.assert_called_once_with("internal-token", {"type": "network"})
        module.discover_solarman.assert_called_once_with(adapters)
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["scope"], "solar_loggers")

    def test_access_error_is_reported_not_empty_success(self):
        module = types.ModuleType("network_discovery")
        module.discover_solarman = Mock()
        with patch.dict(sys.modules, {"network_discovery": module}), patch.object(agent, "home_assistant_ws_command", side_effect=RuntimeError("Accès réseau indisponible")):
            result = agent.relay_command("internal-token", {"id": "scan", "action": "commissioning.discover_solar"})
        self.assertFalse(result["ok"])
        module.discover_solarman.assert_not_called()
