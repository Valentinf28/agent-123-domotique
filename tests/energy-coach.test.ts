import assert from "node:assert/strict";
import test from "node:test";
import {
  energySnapshotFromInventory,
  type EnergyInventoryItem,
} from "../lib/energy-snapshot.ts";
import { consumptionBreakdownFromInventory } from "../lib/consumption-breakdown.ts";
import { buildCoachActionPlan, buildEnergyInsights, tariffGuidance } from "../lib/energy-insights.ts";

const entity = (
  entityId: string,
  state: string,
  unit?: string,
): EnergyInventoryItem => ({
  entityId,
  name: entityId,
  domain: entityId.split(".")[0],
  state,
  attributes: unit ? { unit_of_measurement: unit } : undefined,
});

test("sépare la borne Lektrico de la consommation historique de la maison", () => {
  const snapshot = energySnapshotFromInventory([
    entity("sensor.shellyem3_483fdac38616_channel_b_power", "3.8", "kW"),
    entity("sensor.1p7k_501290_puissance", "2.3", "kW"),
    // La télémétrie Tesla ne doit pas remplacer la mesure réelle de la borne.
    entity("sensor.tesla_model_x_charger_power", "1.7", "kW"),
  ]);

  assert.equal(snapshot.homeWatts, 1500);
  assert.equal(snapshot.vehicleWatts, 2300);
});

test("utilise Tesla seulement lorsque la mesure Lektrico est indisponible", () => {
  const snapshot = energySnapshotFromInventory([
    entity("sensor.shellyem3_483fdac38616_channel_b_power", "3600", "W"),
    entity("sensor.1p7k_501290_puissance", "unavailable", "kW"),
    entity("sensor.tesla_model_x_charger_power", "2.1", "kW"),
  ]);

  assert.equal(snapshot.homeWatts, 3600);
  assert.equal(snapshot.vehicleWatts, 2100);
});

test("normalise W, kW, Wh et kWh avant stockage", () => {
  const snapshot = energySnapshotFromInventory([
    entity("sensor.onduleur_pv_power", "4.25", "kW"),
    entity("sensor.onduleur_grid_power", "-840", "W"),
    entity("sensor.onduleur_battery_power", "-1.1", "kW"),
    entity("sensor.onduleur_today_production", "12850", "Wh"),
    entity("sensor.1_2_3_home_today_consumption", "9.4", "kWh"),
  ]);

  assert.equal(snapshot.solarWatts, 4250);
  assert.equal(snapshot.gridWatts, -840);
  assert.equal(snapshot.batteryWatts, -1100);
  assert.equal(snapshot.dailyProductionWh, 12850);
  assert.equal(snapshot.dailyConsumptionWh, 9400);
});

test("classe les appareils mesurés et conserve les autres usages de la maison", () => {
  const breakdown = consumptionBreakdownFromInventory([
    entity("sensor.pac_piscine_power", "2.1", "kW"),
    entity("sensor.filtration_power", "680", "W"),
  ], [
    { id: "pac", name: "PAC piscine", category: "pool", icon: "≋", powerWatts: 2100, minimumRunMinutes: 60, priority: 1, enabled: true, powerEntityId: "sensor.pac_piscine_power", showInConsumption: true },
    { id: "filtration", name: "Filtration", category: "filtration", icon: "≈", powerWatts: 680, minimumRunMinutes: 60, priority: 2, enabled: true, powerEntityId: "sensor.filtration_power", showInConsumption: true },
  ], 3500);

  assert.deepEqual(breakdown.map((item) => [item.id, item.watts]), [
    ["pac", 2100],
    ["filtration", 680],
    ["other-home", 720],
  ]);
  assert.equal(breakdown[0].sharePercent, 60);
});

test("ne compte jamais deux fois une même pince de mesure", () => {
  const breakdown = consumptionBreakdownFromInventory([
    entity("sensor.pince_pac", "2", "kW"),
  ], [
    { id: "pac", name: "PAC", category: "heating", icon: "♨", enabled: true, powerEntityId: "sensor.pince_pac" },
    { id: "duplicate", name: "Ancienne PAC", category: "heating", icon: "♨", enabled: true, powerEntityId: "SENSOR.PINCE_PAC" },
  ], 2500);

  assert.deepEqual(breakdown.map((item) => [item.id, item.watts]), [
    ["pac", 2000],
    ["other-home", 500],
  ]);
});

const snapshot = (overrides: Partial<ReturnType<typeof energySnapshotFromInventory>> = {}) => ({
  solarWatts: 0,
  homeWatts: 900,
  gridWatts: 0,
  batteryPercent: 50,
  batteryWatts: 0,
  filtrationWatts: 0,
  hotWaterWatts: 0,
  vehicleWatts: 0,
  dailyProductionWh: 0,
  dailyConsumptionWh: 0,
  ...overrides,
});

test("n'invente pas d'économies en euros sans tarif renseigné", () => {
  const history = Array.from({ length: 8 }, (_, index) => ({
    capturedAt: `2026-08-08T0${index % 4}:00:00.000Z`,
    homeWatts: 650,
  }));
  const insights = buildEnergyInsights(snapshot(), history);
  const nightBase = insights.find((insight) => insight.id === "night-base");

  assert.ok(nightBase);
  assert.match(nightBase.impact, /kWh \/ mois/);
  assert.doesNotMatch(nightBase.impact, /€|EUR/);
  assert.equal(nightBase.confidence, "estimated");
});

test("alerte quand la batterie alimente la maison sans solaire près de sa réserve", () => {
  const insights = buildEnergyInsights(snapshot({
    batteryPercent: 36,
    batteryWatts: 1150,
    solarWatts: 0,
  }), [], [], 25);
  const alert = insights.find((insight) => insight.id === "battery-evening-discharge");

  assert.ok(alert);
  assert.equal(alert.goal, "battery");
  assert.equal(alert.confidence, "measured");
  assert.match(alert.description, /1[\s ]?150 W/);
});

test("agit avant que la batterie soit presque vide le soir", () => {
  const insights = buildEnergyInsights(snapshot({
    batteryPercent: 56,
    batteryWatts: 1219,
    solarWatts: 0,
  }), [], [], 25);

  assert.ok(insights.some((insight) => insight.id === "battery-evening-discharge"));
});

test("équilibre les priorités économies, batterie et solaire", () => {
  const insights = buildEnergyInsights(snapshot({
    batteryPercent: 35,
    batteryWatts: 900,
    dailyProductionWh: 8500,
    dailyConsumptionWh: 11000,
  }), [], [{
    id: "pac",
    name: "PAC piscine",
    category: "pool",
    icon: "≋",
    watts: 2100,
    sharePercent: 70,
  }], 25);

  assert.deepEqual(insights.slice(0, 3).map((insight) => insight.goal), [
    "money",
    "battery",
    "solar",
  ]);
});

test("utilise les vraies heures creuses sans inventer leur prix", () => {
  const advice = tariffGuidance("hp_hc", [{ start: "22:30", end: "06:30" }]);

  assert.match(advice, /22:30–06:30/);
  assert.match(advice, /solution de repli/);
  assert.match(advice, /ne peut pas être calculé honnêtement/);
  assert.doesNotMatch(advice, /\d+[,.]?\d*\s*€/);
});

test("ne prétend pas qu'un simple décalage fait économiser avec l'option Base", () => {
  const advice = tariffGuidance("base", []);

  assert.match(advice, /décaler un usage ne réduit pas son prix/);
  assert.match(advice, /prioriser le solaire/);
});

test("prépare le plan pendant les quatorze premiers jours", () => {
  const plan = buildCoachActionPlan({
    learningDays: 8,
    historySamples: 1800,
    insights: [],
    batteryReservePercent: 25,
    tariffPlan: "base",
  });

  assert.equal(plan.status, "learning");
  assert.equal(plan.daysRemaining, 6);
  assert.deepEqual(plan.actions, []);
});

test("débloque après deux semaines un plan 30 jours avec trois priorités", () => {
  const plan = buildCoachActionPlan({
    learningDays: 14,
    historySamples: 3000,
    insights: buildEnergyInsights(snapshot({
      batteryPercent: 55,
      batteryWatts: 900,
      dailyProductionWh: 7500,
      dailyConsumptionWh: 10000,
    }), []),
    batteryReservePercent: 25,
    tariffPlan: "hp_hc",
  });

  assert.equal(plan.status, "ready");
  assert.match(plan.title, /30 prochains jours/);
  assert.deepEqual(plan.actions.map((action) => action.goal), ["money", "battery", "solar"]);
  assert.equal(plan.actions.length, 3);
});

test("ne débloque pas un plan sur un historique trop incomplet", () => {
  const plan = buildCoachActionPlan({
    learningDays: 14,
    historySamples: 200,
    insights: [],
    batteryReservePercent: 25,
    tariffPlan: "base",
  });

  assert.equal(plan.status, "learning");
});
