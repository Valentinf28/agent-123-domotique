import assert from "node:assert/strict";
import test from "node:test";
import {
  energySnapshotFromInventory,
  type EnergyInventoryItem,
} from "../lib/energy-snapshot.ts";
import { consumptionBreakdownFromInventory } from "../lib/consumption-breakdown.ts";

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
