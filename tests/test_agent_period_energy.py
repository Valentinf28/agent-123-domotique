from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_period", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class PeriodEnergyTests(unittest.TestCase):
    def test_period_starts_follow_the_house_timezone(self):
        current = datetime(2026, 7, 31, 14, 22, tzinfo=ZoneInfo("Europe/Paris"))
        starts = agent.energy_period_starts(current)
        self.assertEqual(starts["daily"].isoformat(), "2026-07-31T00:00:00+02:00")
        self.assertEqual(starts["monthly"].isoformat(), "2026-07-01T00:00:00+02:00")
        self.assertEqual(starts["yearly"].isoformat(), "2026-01-01T00:00:00+01:00")


if __name__ == "__main__":
    unittest.main()
