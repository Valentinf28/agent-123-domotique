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
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_lektrico", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


ENTITIES = {
    "gridPowerEntityId": "sensor.shellyem3_483fdac38616_channel_c_power",
    "batteryPowerEntityId": "sensor.onduleur_battery_power",
    "batteryLevelEntityId": "sensor.batterie_deye_soc",
    "chargerStateEntityId": "sensor.1p7k_501290_state",
    "chargerCurrentEntityId": "sensor.1p7k_501290_courant",
    "chargerVoltageEntityId": "sensor.1p7k_501290_tension",
    "dynamicLimitEntityId": "number.1p7k_501290_dynamic_limit",
    "startButtonEntityId": "button.1p7k_501290_charge_start",
    "stopButtonEntityId": "button.1p7k_501290_charge_stop",
    "faultEntityIds": ["binary_sensor.1p7k_501290_ev_error"],
}


class LektricoSolarPlanTests(unittest.TestCase):
    def test_creates_a_local_dynamic_limit_automation(self):
        available = [
            {"entity_id": entity_id, "state": "off", "attributes": {}}
            for key, value in ENTITIES.items()
            for entity_id in (value if key == "faultEntityIds" else [value])
        ]
        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/states"):
                return available
            return {}

        with patch.object(agent, "request_json", side_effect=fake_request):
            response = agent.relay_command(
                "token",
                {
                    "id": "test",
                    "action": "ha.ev_charger.solar_plan",
                    "payload": {**ENTITIES, "reserveWatts": 100, "maximumAmps": 32},
                },
            )

        self.assertEqual(response["type"], "command.result")
        self.assertTrue(response["ok"])
        automation_call = next(
            kwargs for url, kwargs in calls
            if "/config/automation/config/ma_maison_lektrico_solar_charging" in url
        )
        automation = automation_call["payload"]
        self.assertEqual(automation["mode"], "restart")
        self.assertEqual(automation["trigger"][0]["seconds"], "/5")
        serialized = str(automation)
        self.assertIn("number.1p7k_501290_dynamic_limit", serialized)
        self.assertIn("button.1p7k_501290_charge_start", serialized)
        self.assertIn("button.1p7k_501290_charge_stop", serialized)
        self.assertIn("-grid - 100", serialized)
        self.assertIn("'need_auth'", serialized)
        self.assertIn("'paused_by_scheduler'", serialized)
        self.assertIn("sensor.batterie_deye_soc", serialized)
        self.assertIn(">= 95", serialized)
        self.assertIn("sensor.onduleur_battery_power", serialized)
        self.assertIn("battery_discharge", serialized)
        self.assertEqual(automation["trigger"][1]["for"]["seconds"], 15)
        self.assertEqual(automation["trigger"][2]["for"]["seconds"], 45)
        stop_choice = automation["action"][0]["choose"][0]
        self.assertEqual(
            stop_choice["sequence"],
            [{
                "service": "button.press",
                "target": {"entity_id": "button.1p7k_501290_charge_stop"},
            }],
        )
        choices = automation["action"][0]["choose"]
        stop_sequences = [
            step for choice in choices for step in choice["sequence"]
            if step.get("target", {}).get("entity_id")
            == "button.1p7k_501290_charge_stop"
        ]
        self.assertEqual(len(stop_sequences), 1)
        retry_choice = choices[-1]
        self.assertIn("now().second", str(retry_choice["conditions"]))
        self.assertEqual(
            retry_choice["sequence"][-1]["target"]["entity_id"],
            "button.1p7k_501290_charge_start",
        )
        self.assertNotIn("'value': 0", serialized)

    def test_keeps_battery_sensors_optional(self):
        payload = {
            key: value for key, value in ENTITIES.items()
            if key not in {"batteryPowerEntityId", "batteryLevelEntityId"}
        }
        available = [
            {"entity_id": entity_id, "state": "off", "attributes": {}}
            for key, value in payload.items()
            for entity_id in (value if key == "faultEntityIds" else [value])
        ]

        def fake_request(url, **kwargs):
            return available if url.endswith("/states") else {}

        with patch.object(agent, "request_json", side_effect=fake_request):
            response = agent.relay_command(
                "token",
                {
                    "id": "test",
                    "action": "ha.ev_charger.solar_plan",
                    "payload": payload,
                },
            )

        self.assertTrue(response["ok"])

    def test_refuses_an_unknown_charger_entity(self):
        with patch.object(agent, "request_json", return_value=[]):
            response = agent.relay_command(
                "token",
                {
                    "id": "test",
                    "action": "ha.ev_charger.solar_plan",
                    "payload": ENTITIES,
                },
            )

        self.assertEqual(response["type"], "command.result")
        self.assertFalse(response["ok"])
        self.assertIn("introuvable", response["error"])


if __name__ == "__main__":
    unittest.main()
