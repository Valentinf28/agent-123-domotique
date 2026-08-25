from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_registry", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class RegistryInventoryTests(unittest.TestCase):
    def test_joins_only_safe_device_metadata_to_entities(self):
        metadata = agent.registry_metadata_from_results(
            {"result": [{
                "entity_id": "switch.shelly_chauffe_eau",
                "device_id": "device-1",
                "platform": "shelly",
                "original_name": "Switch 0",
            }]},
            {"result": [{
                "id": "device-1",
                "name_by_user": "Chauffe-eau",
                "manufacturer": "Shelly",
                "model": "Pro 1PM",
                "serial_number": "ABC123",
                "configuration_url": "http://192.168.1.10",
            }]},
        )
        entity = metadata["switch.shelly_chauffe_eau"]
        self.assertEqual(entity["manufacturer"], "Shelly")
        self.assertEqual(entity["model"], "Pro 1PM")
        self.assertEqual(entity["device_name"], "Chauffe-eau")
        self.assertNotIn("configuration_url", entity)

    def test_ignores_registry_rows_without_entity_id(self):
        metadata = agent.registry_metadata_from_results(
            {"result": [{"device_id": "device-1"}]},
            {"result": [{"id": "device-1", "manufacturer": "Shelly"}]},
        )
        self.assertEqual(metadata, {})

    def test_enriches_only_full_inventory_with_registry_metadata(self):
        config = {"version": "2026.8.0", "time_zone": "Europe/Paris"}
        states = [{
            "entity_id": "switch.chauffe_eau",
            "state": "on",
            "attributes": {"friendly_name": "Chauffe-eau"},
        }]

        def fake_request(url, **_kwargs):
            return config if url.endswith("/config") else states

        common_patches = (
            patch.object(agent, "request_json", side_effect=fake_request),
            patch.object(agent, "maintain_daily_pv_peak"),
            patch.object(agent, "shelly_daily_energy_inventory", return_value=[]),
            patch.object(agent, "device_daily_energy_inventory", return_value=[]),
            patch.object(agent, "period_energy_inventory", return_value=[]),
            patch.object(agent, "solar_forecast_inventory", return_value=[]),
        )
        with common_patches[0], common_patches[1], common_patches[2], common_patches[3], \
                common_patches[4], common_patches[5], patch.object(
                    agent,
                    "home_assistant_registry_metadata",
                    return_value={"switch.chauffe_eau": {"platform": "shelly"}},
                ) as registry:
            full = agent.home_assistant_summary("token", full_inventory=True)
            fast = agent.home_assistant_summary("token", full_inventory=False)

        self.assertEqual(full["inventory"][0]["attributes"]["platform"], "shelly")
        self.assertNotIn("platform", fast["inventory"][0]["attributes"])
        registry.assert_called_once_with("token")

    def test_fast_inventory_keeps_automation_trigger_for_remote_notifications(self):
        config = {"version": "2026.8.0", "time_zone": "Europe/Paris"}
        states = [{
            "entity_id": "automation.couper_filtration",
            "state": "on",
            "attributes": {
                "friendly_name": "Couper la filtration",
                "last_triggered": "2026-08-26T08:15:00+00:00",
            },
        }]

        def fake_request(url, **_kwargs):
            return config if url.endswith("/config") else states

        with patch.object(agent, "request_json", side_effect=fake_request), \
                patch.object(agent, "maintain_daily_pv_peak"):
            summary = agent.home_assistant_summary("token", full_inventory=False)

        self.assertEqual(summary["agentVersion"], "0.6.0")
        self.assertEqual(summary["inventory"][0]["entityId"], "automation.couper_filtration")
        self.assertEqual(
            summary["inventory"][0]["attributes"]["last_triggered"],
            "2026-08-26T08:15:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
