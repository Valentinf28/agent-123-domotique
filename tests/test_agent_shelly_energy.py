from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_shelly", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class ShellyDailyEnergyTests(unittest.TestCase):
    def test_computes_delta_from_first_state_of_day(self):
        history = [[
            {"state": "15995.2039"},
            {"state": "16000.1000"},
        ]]
        self.assertEqual(
            agent.daily_energy_delta("16013.5715", history),
            18.3676,
        )

    def test_ignores_invalid_or_reset_meter(self):
        self.assertIsNone(agent.daily_energy_delta("unknown", [[{"state": "10"}]]))
        self.assertIsNone(agent.daily_energy_delta("5", [[{"state": "10"}]]))
        self.assertIsNone(agent.daily_energy_delta("12", []))


if __name__ == "__main__":
    unittest.main()
