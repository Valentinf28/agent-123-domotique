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
        self.assertEqual(automation["trigger"][0]["seconds"], "/15")
        serialized = str(automation)
        self.assertIn("number.1p7k_501290_dynamic_limit", serialized)
        self.assertIn("button.1p7k_501290_charge_start", serialized)
        self.assertIn("button.1p7k_501290_charge_stop", serialized)
        self.assertIn("-grid - 100", serialized)

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
