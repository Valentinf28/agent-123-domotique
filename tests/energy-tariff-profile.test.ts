import assert from "node:assert/strict";
import test from "node:test";
import {
  sanitizeEnergyTariff,
  sanitizeOffPeakPeriods,
  sanitizeTariffPlan,
} from "../lib/energy-tariff-profile.ts";

test("conserve uniquement des plages horaires technicien valides", () => {
  assert.deepEqual(sanitizeOffPeakPeriods([
    { start: "01:30", end: "07:15" },
    { start: "12:45", end: "14:15" },
    { start: "soir", end: "matin" },
    { start: "12:00", end: "12:00" },
  ]), [
    { start: "01:30", end: "07:15" },
    { start: "12:45", end: "14:15" },
  ]);
});

test("ne remplace jamais un prix manquant par un tarif fictif", () => {
  assert.deepEqual(sanitizeEnergyTariff({ peakPrice: "0,2146", offPeakPrice: "" }), {
    basePrice: null,
    peakPrice: 0.2146,
    offPeakPrice: null,
  });
  assert.equal(sanitizeTariffPlan("inconnu"), "base");
});
