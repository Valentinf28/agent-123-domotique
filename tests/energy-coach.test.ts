import assert from "node:assert/strict";
import test from "node:test";
import {
  energyInsights,
  type EnergyInsightSnapshot,
  type EnergyHistorySample,
} from "../lib/energy-insights.ts";

const current = (overrides: Partial<EnergyInsightSnapshot> = {}): EnergyInsightSnapshot => ({
  solarWatts: 0,
  homeWatts: 0,
  gridWatts: 0,
  batteryPercent: 0,
  batteryWatts: 0,
  filtrationWatts: 0,
  hotWaterWatts: 0,
  vehicleWatts: 0,
  dailyProductionWh: 0,
  dailyConsumptionWh: 0,
  ...overrides,
});

const sample = (capturedAt: string, homeWatts = 400): EnergyHistorySample => ({
  capturedAt,
  solarWatts: 0,
  homeWatts,
  gridWatts: 0,
  batteryPercent: 50,
  batteryWatts: 0,
  filtrationWatts: 0,
  hotWaterWatts: 0,
  vehicleWatts: 0,
  dailyProductionWh: 0,
  dailyConsumptionWh: 0,
});

test("utilise l'injection réseau réelle et tient compte de la batterie", () => {
  const chargingBattery = energyInsights(current({
    solarWatts: 5_000,
    homeWatts: 2_000,
    gridWatts: 0,
    batteryWatts: 3_000,
    batteryPercent: 95,
  }), []);
  assert.equal(chargingBattery.some((insight) => insight.id === "solar-surplus"), false);

  const exporting = energyInsights(current({
    solarWatts: 5_000,
    homeWatts: 2_000,
    gridWatts: -1_200,
    batteryPercent: 95,
  }), []);
  assert.equal(exporting.find((insight) => insight.id === "solar-surplus")?.description,
    "1200 W sont réellement injectés et peuvent alimenter un équipement flexible maintenant.");
});

test("analyse la nuit selon le fuseau de la maison", () => {
  // En été, 22:30 UTC correspond à 00:30 à Paris.
  const history = Array.from({ length: 8 }, (_, index) =>
    sample(`2026-07-${String(index + 1).padStart(2, "0")}T22:30:00.000Z`));
  const paris = energyInsights(current(), history, "Europe/Paris");
  const utc = energyInsights(current(), history, "UTC");
  assert.equal(paris.find((insight) => insight.id === "night-base")?.impact,
    "Jusqu’à 38 kWh / mois à examiner");
  assert.equal(utc.some((insight) => insight.id === "night-base"), false);
});

test("attend assez de relevés avant de déclarer une anomalie nocturne", () => {
  const history = Array.from({ length: 7 }, (_, index) =>
    sample(`2026-07-${String(index + 1).padStart(2, "0")}T22:30:00.000Z`));
  assert.equal(energyInsights(current(), history).some((insight) => insight.id === "night-base"), false);
});

test("ne présente pas le ratio production consommation comme une autonomie", () => {
  const result = energyInsights(current({
    dailyProductionWh: 5_000,
    dailyConsumptionWh: 10_000,
  }), []);
  assert.equal(result.find((insight) => insight.id === "daily-balance")?.impact,
    "Production équivalente à 50 % de la consommation");
});
