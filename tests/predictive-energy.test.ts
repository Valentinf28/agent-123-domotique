import assert from "node:assert/strict";
import test from "node:test";
import { buildPredictiveEnergyPlan, type SolarForecastSlot } from "../lib/predictive-energy.ts";

const now = new Date("2026-07-29T08:00:00.000Z");

function hourlyForecast(values: number[]): SolarForecastSlot[] {
  return values.map((estimatedWh, index) => ({
    startsAt: new Date(now.getTime() + index * 60 * 60 * 1000).toISOString(),
    estimatedWh,
  }));
}

function scenario(overrides: Partial<Parameters<typeof buildPredictiveEnergyPlan>[0]> = {}) {
  return buildPredictiveEnergyPlan({
    now,
    batteryPercent: 80,
    baseLoadWatts: 500,
    forecast: hourlyForecast([200, 400, 800, 1500, 2500, 3000, 2500, 1800, 900, 300, 0, 0]),
    settings: {
      batteryCapacityWh: 15_000,
      batteryReservePercent: 25,
    },
    load: {
      id: "pac-piscine",
      label: "PAC piscine",
      category: "pool",
      powerWatts: 2_000,
      minimumRunMinutes: 60,
      alreadyRunning: false,
      needed: true,
    },
    ...overrides,
  });
}

test("anticipe la PAC quand le soleil futur rechargera la batterie", () => {
  const plan = scenario();
  assert.equal(plan.status, "ready_now");
  assert.equal(plan.flexibleLoadEnergyWh, 2_000);
  assert.ok(plan.projectedMinimumBatteryPercent >= 25);
  assert.ok(plan.forecastNextSixHoursWh > 5_000);
});

test("protège la batterie quand la prévision est faible", () => {
  const plan = scenario({
    batteryPercent: 30,
    forecast: hourlyForecast([50, 80, 100, 120, 100, 80, 50, 0]),
  });
  assert.equal(plan.status, "protected");
  assert.ok(plan.projectedMinimumBatteryPercent >= 25);
});

test("ne chauffe pas une piscine déjà à la consigne", () => {
  const plan = scenario({
    load: {
      id: "pac-piscine",
      label: "PAC piscine",
      category: "pool",
      powerWatts: 2_000,
      minimumRunMinutes: 60,
      alreadyRunning: false,
      needed: false,
      needReason: "La piscine est déjà à sa consigne.",
    },
  });
  assert.equal(plan.status, "no_need");
});

test("utilise le même moteur pour un chauffe-eau", () => {
  const plan = scenario({
    load: {
      id: "chauffe-eau",
      label: "Chauffe-eau",
      category: "hot_water",
      powerWatts: 2_400,
      minimumRunMinutes: 90,
      alreadyRunning: false,
      needed: true,
    },
  });
  assert.equal(plan.loadLabel, "Chauffe-eau");
  assert.equal(plan.status, "ready_now");
  assert.equal(plan.flexibleLoadEnergyWh, 3_600);
});

test("demande Forecast.Solar quand aucune courbe n’est disponible", () => {
  const plan = scenario({ forecast: [] });
  assert.equal(plan.status, "needs_forecast");
});
