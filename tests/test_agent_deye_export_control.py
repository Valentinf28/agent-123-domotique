from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_deye", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


STATES = [
    {
        "entity_id": "sensor.1p7k_501290_state",
        "state": "connected",
        "attributes": {"friendly_name": "Lektrico State"},
    },
    {
        "entity_id": "switch.inverter_solar_sell",
        "state": "on",
        "attributes": {"friendly_name": "Deye Solar Sell"},
    },
]


PAYLOAD = {
    "manageInverterExport": True,
    "chargerStateEntityId": "sensor.1p7k_501290_state",
    "inverterExportSwitchEntityId": "switch.inverter_solar_sell",
}


class DeyeVehicleExportPolicyTests(unittest.TestCase):
    def test_is_disabled_without_explicit_opt_in(self):
        self.assertIsNone(agent.deye_vehicle_export_automation({}, STATES))

    def test_builds_debounced_plug_and_unplug_sequences(self):
        automation = agent.deye_vehicle_export_automation(PAYLOAD, STATES)

        self.assertEqual(automation["id"], "ma_maison_deye_vehicle_export_policy")
        self.assertEqual(automation["mode"], "restart")
        triggers = {trigger.get("id"): trigger for trigger in automation["trigger"]}
        self.assertEqual(triggers["voiture_branchee"]["for"]["seconds"], 10)
        self.assertEqual(triggers["voiture_debranchee"]["for"]["seconds"], 30)
        self.assertEqual(triggers["reconciliation"]["seconds"], "/15")
        sequences = automation["action"][0]["choose"]
        self.assertEqual(
            sequences[0]["sequence"],
            [
                {
                    "service": "switch.turn_on",
                    "target": {"entity_id": "switch.inverter_solar_sell"},
                },
            ],
        )
        self.assertEqual(
            automation["action"][0]["default"],
            [
                {
                    "service": "switch.turn_off",
                    "target": {"entity_id": "switch.inverter_solar_sell"},
                },
            ],
        )
        self.assertIn("not in", triggers["voiture_debranchee"]["value_template"])

    def test_unknown_or_idle_state_fails_safe_with_export_disabled(self):
        automation = agent.deye_vehicle_export_automation(PAYLOAD, STATES)

        self.assertEqual(
            automation["action"][0]["default"],
            [{
                "service": "switch.turn_off",
                "target": {"entity_id": "switch.inverter_solar_sell"},
            }],
        )
        self.assertNotIn("idle", automation["trigger"][2]["value_template"])

    def test_rejects_an_unrelated_switch(self):
        states = [*STATES[:-1], {
            "entity_id": "switch.bad_command",
            "state": "on",
            "attributes": {"friendly_name": "Garden light"},
        }]
        with self.assertRaisesRegex(ValueError, "Solar Sell"):
            agent.deye_vehicle_export_automation(
                {**PAYLOAD, "inverterExportSwitchEntityId": "switch.bad_command"},
                states,
            )

    def test_requires_the_dedicated_solar_sell_switch(self):
        with self.assertRaisesRegex(ValueError, "Solar Sell"):
            agent.deye_vehicle_export_automation(
                {**PAYLOAD, "inverterExportSwitchEntityId": ""},
                STATES,
            )


if __name__ == "__main__":
    unittest.main()
