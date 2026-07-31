from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import types
import unittest


AGENT_PATH = Path(__file__).parents[1] / "agent_123_domotique" / "agent.py"
if "websocket" not in sys.modules:
    sys.modules["websocket"] = types.ModuleType("websocket")
SPEC = importlib.util.spec_from_file_location("agent_123_domotique_peak", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


def pv_state(value: str, unit: str = "W"):
    return {
        "entity_id": "sensor.onduleur_pv_power",
        "state": value,
        "attributes": {"unit_of_measurement": unit},
    }


class DailyPvPeakTests(unittest.TestCase):
    def test_keeps_the_highest_value_during_the_same_day(self):
        result = agent.daily_pv_peak(
            [pv_state("3150")],
            {"date": "2026-07-31", "peak_w": 4870},
            now=datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result, {"date": "2026-07-31", "peak_w": 4870.0})

    def test_resets_when_the_local_date_changes(self):
        result = agent.daily_pv_peak(
            [pv_state("0")],
            {"date": "2026-07-30", "peak_w": 9096},
            now=datetime(2026, 7, 30, 22, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result, {"date": "2026-07-31", "peak_w": 0.0})

    def test_converts_kw_to_watts(self):
        result = agent.daily_pv_peak(
            [pv_state("4.25", "kW")],
            {},
            now=datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["peak_w"], 4250.0)


if __name__ == "__main__":
    unittest.main()
