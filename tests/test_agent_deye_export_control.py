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


def states(export_name: str = "Deye Solar Sell") -> list[dict]:
    return [
        {
            "entity_id": "sensor.lektrico_vehicle_state",
            "state": "connected",
            "attributes": {"friendly_name": "État véhicule Lektrico"},
        },
        {
            "entity_id": "switch.onduleur_solar_sell",
            "state": "on",
            "attributes": {"friendly_name": export_name},
        },
    ]


def payload(enabled: bool = True) -> dict:
    return {
        "manageInverterExport": enabled,
        "chargerStateEntityId": "sensor.lektrico_vehicle_state",
        "inverterExportSwitchEntityId": "switch.onduleur_solar_sell",
    }


class DeyeExportControlTests(unittest.TestCase):
    def test_policy_is_strictly_opt_in(self) -> None:
        self.assertIsNone(agent.deye_vehicle_export_automation(payload(False), states()))

    def test_policy_exports_only_while_charging_and_probes_briefly(self) -> None:
        automation = agent.deye_vehicle_export_automation(payload(), states())
        self.assertIsNotNone(automation)
        self.assertTrue(automation["initial_state"])
        self.assertEqual(automation["trigger"][1]["for"]["seconds"], 3)
        self.assertEqual(automation["trigger"][2]["for"]["seconds"], 10)
        self.assertEqual(automation["trigger"][3]["minutes"], "/5")
        self.assertEqual(automation["trigger"][4]["seconds"], "/15")
        choices = automation["action"][0]["choose"]
        self.assertEqual(choices[0]["sequence"][0], {
            "service": "switch.turn_on",
            "target": {"entity_id": "switch.onduleur_solar_sell"},
        })
        self.assertEqual(choices[1]["sequence"][0], {
            "service": "switch.turn_off",
            "target": {"entity_id": "switch.onduleur_solar_sell"},
        })
        self.assertEqual(choices[2]["sequence"][0]["service"], "switch.turn_off")
        self.assertIn("not in", choices[2]["conditions"][1]["value_template"])
        self.assertEqual(choices[3]["sequence"][0]["service"], "switch.turn_on")
        self.assertEqual(choices[3]["sequence"][1]["delay"]["seconds"], 35)
        self.assertEqual(choices[3]["sequence"][-1]["service"], "switch.turn_off")

    def test_policy_rejects_an_unrelated_switch(self) -> None:
        current_payload = payload()
        current_payload["inverterExportSwitchEntityId"] = "switch.pompe_piscine"
        current_states = states("Pompe piscine")
        current_states[1]["entity_id"] = "switch.pompe_piscine"
        with self.assertRaisesRegex(ValueError, "Solar Sell"):
            agent.deye_vehicle_export_automation(current_payload, current_states)

    def test_policy_requires_the_solar_sell_switch(self) -> None:
        current_payload = payload()
        current_payload["inverterExportSwitchEntityId"] = ""
        with self.assertRaisesRegex(ValueError, "indispensable"):
            agent.deye_vehicle_export_automation(current_payload, states())

    def test_initial_sync_blocks_export_for_a_waiting_vehicle(self) -> None:
        self.assertEqual(
            agent.deye_vehicle_export_sync_service(payload(), states()),
            "turn_off",
        )

    def test_initial_sync_enables_export_during_active_charge(self) -> None:
        current_states = states()
        current_states[0]["state"] = "charging"
        self.assertEqual(
            agent.deye_vehicle_export_sync_service(payload(), current_states),
            "turn_on",
        )

    def test_initial_sync_blocks_export_for_an_unplugged_vehicle(self) -> None:
        current_states = states()
        current_states[0]["state"] = "available"
        self.assertEqual(
            agent.deye_vehicle_export_sync_service(payload(), current_states),
            "turn_off",
        )

    def test_initial_sync_blocks_export_for_an_unknown_state(self) -> None:
        current_states = states()
        current_states[0]["state"] = "unavailable"
        self.assertEqual(
            agent.deye_vehicle_export_sync_service(payload(), current_states),
            "turn_off",
        )
