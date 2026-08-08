from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo


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
        self.assertIsNone(agent.daily_energy_delta("nan", [[{"state": "10"}]]))
        self.assertIsNone(agent.daily_energy_delta("-1", [[{"state": "10"}]]))
        self.assertIsNone(agent.daily_energy_delta("12", []))

    def test_keeps_energy_accumulated_across_a_meter_reset(self):
        history = [[
            {"state": "100"},
            {"state": "104.5"},
            {"state": "0.2"},
            {"state": "2.0"},
        ]]
        self.assertEqual(agent.daily_energy_delta("3.0", history), 7.5)

    def test_ignores_small_counter_jitter(self):
        history = [[
            {"state": "100"},
            {"state": "100.05"},
            {"state": "100.04"},
        ]]
        self.assertEqual(agent.daily_energy_delta("100.08", history), 0.08)

    def test_daily_solar_peak_keeps_the_persisted_maximum_and_converts_kw(self):
        current = {
            "entity_id": "sensor.onduleur_pv_power",
            "state": "1.2",
            "attributes": {"unit_of_measurement": "kW"},
        }
        now = datetime(2026, 8, 2, 14, 7, tzinfo=ZoneInfo("Europe/Paris"))
        result = agent.daily_pv_peak(
            [current],
            {"date": "2026-08-02", "peak_w": 4850},
            now=now,
        )
        self.assertEqual(result, {"date": "2026-08-02", "peak_w": 4850.0})

    def test_daily_solar_peak_resets_to_the_current_day(self):
        now = datetime(2026, 8, 2, 14, 7, tzinfo=ZoneInfo("Europe/Paris"))
        states = [{
            "entity_id": "sensor.onduleur_pv_power",
            "state": "3200",
            "attributes": {"unit_of_measurement": "W"},
        }]
        result = agent.daily_pv_peak(
            states,
            {"date": "2026-08-01", "peak_w": 9000},
            now=now,
        )
        self.assertEqual(result, {"date": "2026-08-02", "peak_w": 3200.0})

    def test_period_starts_use_the_house_local_timezone(self):
        current = datetime(2026, 7, 31, 14, 22, tzinfo=ZoneInfo("Europe/Paris"))
        starts = agent.energy_period_starts(current)
        self.assertEqual(starts["daily"].isoformat(), "2026-07-31T00:00:00+02:00")
        self.assertEqual(starts["monthly"].isoformat(), "2026-07-01T00:00:00+02:00")
        self.assertEqual(starts["yearly"].isoformat(), "2026-01-01T00:00:00+01:00")


if __name__ == "__main__":
    unittest.main()
