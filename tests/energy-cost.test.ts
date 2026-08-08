import assert from "node:assert/strict";
import test from "node:test";
import { measuredGridCost } from "../lib/energy-cost";

const prices = {
  baseMilliEurosPerKwh: 250,
  peakMilliEurosPerKwh: 300,
  offPeakMilliEurosPerKwh: 200,
  exportMilliEurosPerKwh: 50,
};

test("chiffre uniquement les achats réseau et déduit l’injection rémunérée", () => {
  const result = measuredGridCost({
    plan: "base",
    periods: [],
    prices,
    samples: [
      { capturedAt: "2026-08-08T10:00:00.000Z", gridWatts: 2000 },
      { capturedAt: "2026-08-08T10:15:00.000Z", gridWatts: -1000 },
      { capturedAt: "2026-08-08T10:30:00.000Z", gridWatts: 0 },
    ],
  });
  assert.equal(result.importedWh, 500);
  assert.equal(result.exportedWh, 250);
  assert.equal(result.importCostEuros, 0.125);
  assert.equal(result.exportRevenueEuros, 0.0125);
  assert.equal(result.netEnergyCostEuros, 0.1125);
});

test("applique réellement les heures creuses, y compris après minuit", () => {
  const result = measuredGridCost({
    plan: "hp_hc",
    periods: [{ start: "22:30", end: "06:30" }],
    prices,
    samples: [
      { capturedAt: "2026-08-08T23:00:00.000Z", gridWatts: 1000 },
      { capturedAt: "2026-08-08T23:15:00.000Z", gridWatts: 1000 },
      { capturedAt: "2026-08-08T23:30:00.000Z", gridWatts: 0 },
    ],
  });
  assert.equal(result.importedWh, 500);
  assert.equal(result.importCostEuros, 0.1);
});

test("refuse un montant incomplet lorsqu’un prix nécessaire manque", () => {
  const result = measuredGridCost({
    plan: "base",
    periods: [],
    prices: { ...prices, baseMilliEurosPerKwh: null },
    samples: [
      { capturedAt: "2026-08-08T10:00:00.000Z", gridWatts: 1000 },
      { capturedAt: "2026-08-08T10:15:00.000Z", gridWatts: 0 },
    ],
  });
  assert.equal(result.importCostEuros, null);
  assert.equal(result.netEnergyCostEuros, null);
});
