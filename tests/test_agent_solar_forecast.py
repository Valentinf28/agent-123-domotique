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
SPEC = importlib.util.spec_from_file_location("agent_123_domotique", AGENT_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


def forecast_state(entity_id: str, value: str, unit: str | None = None):
    attributes = {}
    if unit:
        attributes["unit_of_measurement"] = unit
    return {
        "entity_id": entity_id,
        "state": value,
        "attributes": attributes,
    }


class SolarForecastFallbackTests(unittest.TestCase):
    def test_builds_24_slots_and_preserves_aggregate_energy(self):
        states = [
            forecast_state("sensor.energy_current_hour", "0.2", "kWh"),
            forecast_state("sensor.energy_next_hour", "0.5", "kWh"),
            forecast_state("sensor.energy_production_next_12hours", "8.4", "kWh"),
            forecast_state("sensor.energy_production_next_24hours", "15.7", "kWh"),
            forecast_state(
                "sensor.power_highest_peak_time_today",
                "2026-07-29T12:30:00+02:00",
            ),
            forecast_state(
                "sensor.power_highest_peak_time_tomorrow",
                "2026-07-30T11:45:00+02:00",
            ),
        ]
        entries = agent.fallback_solar_forecast_inventory(
            states,
            now=datetime(2026, 7, 29, 8, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(len(entries), 24)
        values = [int(item["state"]) for item in entries]
        self.assertAlmostEqual(sum(values[:12]), 8400, delta=5)
        self.assertAlmostEqual(sum(values), 15700, delta=10)
        self.assertEqual(values[0], 200)
        self.assertEqual(values[1], 500)
        self.assertTrue(all(item["name"].startswith("Prévision solaire ") for item in entries))

    def test_accepts_wh_units_without_multiplying(self):
        states = [
            forecast_state("sensor.energy_production_next_12hours", "900", "Wh"),
            forecast_state("sensor.energy_production_next_24hours", "1200", "Wh"),
        ]
        entries = agent.fallback_solar_forecast_inventory(
            states,
            now=datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc),
        )

        self.assertAlmostEqual(sum(int(item["state"]) for item in entries), 1200, delta=10)

    def test_uses_default_today_and_tomorrow_sensors(self):
        states = [
            forecast_state("sensor.energy_production_today_remaining", "0", "kWh"),
            forecast_state("sensor.energy_production_tomorrow", "18.2", "kWh"),
            forecast_state(
                "sensor.power_highest_peak_time_tomorrow",
                "2026-07-30T11:30:00+02:00",
            ),
        ]
        entries = agent.fallback_solar_forecast_inventory(
            states,
            now=datetime(2026, 7, 29, 21, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(len(entries), 24)
        self.assertAlmostEqual(
            sum(int(item["state"]) for item in entries),
            18200,
            delta=25,
        )
        self.assertGreater(max(int(item["state"]) for item in entries), 1000)

    def test_returns_empty_without_forecast_sensors(self):
        self.assertEqual(agent.fallback_solar_forecast_inventory([]), [])


if __name__ == "__main__":
    unittest.main()
