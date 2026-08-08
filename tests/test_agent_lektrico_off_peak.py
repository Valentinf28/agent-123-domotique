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
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_off_peak", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


PAYLOAD = {
    "chargerStateEntityId": "sensor.1p7k_501290_state",
    "dynamicLimitEntityId": "number.1p7k_501290_dynamic_limit",
    "startButtonEntityId": "button.1p7k_501290_charge_start",
    "stopButtonEntityId": "button.1p7k_501290_charge_stop",
    "maximumAmps": 32,
    "offPeakPeriods": [
        {"start": "01:30", "end": "07:15"},
        {"start": "12:45", "end": "14:15"},
    ],
}


class LektricoOffPeakPlanTests(unittest.TestCase):
    def test_creates_a_multi_period_automation_that_requires_a_plugged_car(self):
        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            return {}

        with patch.object(agent, "request_json", side_effect=fake_request):
            response = agent.relay_command(
                "token",
                {"id": "test", "action": "ha.ev_charger.off_peak_plan", "payload": PAYLOAD},
            )

        self.assertTrue(response["ok"])
        automation = next(
            kwargs["payload"] for url, kwargs in calls
            if url.endswith("/config/automation/config/ma_maison_lektrico_off_peak_charging")
        )
        self.assertEqual(automation["mode"], "restart")
        trigger_times = [trigger.get("at") for trigger in automation["trigger"] if trigger.get("at")]
        self.assertEqual(trigger_times, ["01:30:00", "07:15:00", "12:45:00", "14:15:00"])
        serialized = str(automation)
        self.assertIn("'connected'", serialized)
        self.assertIn("'finishing'", serialized)
        self.assertIn("'need_auth'", serialized)
        self.assertIn("'locked'", serialized)
        self.assertNotIn("'available'", serialized)
        self.assertIn("90 <= minutes", serialized)
        self.assertIn("minutes < 435", serialized)
        self.assertIn("number.1p7k_501290_dynamic_limit", serialized)
        self.assertIn("button.1p7k_501290_charge_start", serialized)
        self.assertIn("button.1p7k_501290_charge_stop", serialized)

    def test_uses_the_explicit_22_to_6_fallback_without_periods(self):
        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            return {}

        with patch.object(agent, "request_json", side_effect=fake_request):
            response = agent.relay_command(
                "token",
                {
                    "id": "test",
                    "action": "ha.ev_charger.off_peak_plan",
                    "payload": {**PAYLOAD, "offPeakPeriods": []},
                },
            )
        self.assertTrue(response["ok"])
        automation = next(
            kwargs["payload"] for url, kwargs in calls
            if "ma_maison_lektrico_off_peak_charging" in url
        )
        trigger_times = [trigger.get("at") for trigger in automation["trigger"] if trigger.get("at")]
        self.assertEqual(trigger_times, ["22:00:00", "06:00:00"])
        self.assertIn("minutes >= 1320 or minutes < 360", str(automation))

    def test_rejects_an_entity_with_the_wrong_domain(self):
        with patch.object(agent, "request_json", return_value={}):
            response = agent.relay_command(
                "token",
                {
                    "id": "test",
                    "action": "ha.ev_charger.off_peak_plan",
                    "payload": {**PAYLOAD, "dynamicLimitEntityId": "switch.bad_limit"},
                },
            )
        self.assertFalse(response["ok"])
        self.assertIn("Limite dynamique", response["error"])


if __name__ == "__main__":
    unittest.main()
