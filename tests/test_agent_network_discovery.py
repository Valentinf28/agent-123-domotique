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

    def test_installer_accepts_no_remote_path_or_download(self):
        module = types.ModuleType("connector_install")
        module.install_solarman = Mock(return_value={"connector": "solarman", "status": "installed", "configured": False})
        with patch.dict(sys.modules, {"connector_install": module}):
            result = agent.relay_command("internal-token", {
                "id": "install", "action": "commissioning.install_solarman",
                "payload": {"config": "/etc", "bundle": "https://untrusted.example/code.zip"},
            })
        module.install_solarman.assert_called_once_with()
        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["configured"])

    def test_access_error_is_reported_not_empty_success(self):
        module = types.ModuleType("network_discovery")
        module.discover_solarman = Mock()
        with patch.dict(sys.modules, {"network_discovery": module}), patch.object(agent, "home_assistant_ws_command", side_effect=RuntimeError("Accès réseau indisponible")):
            result = agent.relay_command("internal-token", {"id": "scan", "action": "commissioning.discover_solar"})
        self.assertFalse(result["ok"])
        module.discover_solarman.assert_not_called()

    def test_measurement_verification_uses_box_data_not_caller_values(self):
        module = types.ModuleType("solar_measurements")
        module.inspect_measurements = Mock(return_value={"readingsAvailable": False, "physicalTestVerified": False})
        entries = [{"entry_id": "ours"}]
        states = [{"entity_id": "sensor.real"}]
        registry = [{"config_entry_id": "ours"}]
        with patch.dict(sys.modules, {"solar_measurements": module}), patch.object(agent, "home_assistant_ws_command", return_value={"result": registry}), patch.object(agent, "request_json", side_effect=[entries, states]) as requests:
            result = agent.relay_command("internal-token", {
                "id": "verify", "action": "commissioning.verify_deye",
                "payload": {"entryId": "ours", "inverterSerial": "1234567890", "states": [{"fake": True}]},
            })
        module.inspect_measurements.assert_called_once_with("ours", "1234567890", entries, registry, states)
        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["physicalTestVerified"])
        self.assertTrue(all("method" not in call.kwargs for call in requests.call_args_list))
