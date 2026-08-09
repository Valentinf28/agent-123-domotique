import assert from "node:assert/strict";
import test from "node:test";
import { gridExportReleaseCommands } from "../lib/grid-export-control.ts";

test("désactive la politique zéro injection puis autorise Solar Sell", () => {
  assert.deepEqual(gridExportReleaseCommands([
    { entityId: "automation.ma_maison_deye_vehicle_export_policy", name: "1.2.3. Home · Injection Deye selon véhicule" },
    { entityId: "switch.deye_solar_sell", name: "Deye Solar Sell" },
  ]), [
    { domain: "automation", service: "turn_off", entityId: "automation.ma_maison_deye_vehicle_export_policy" },
    { domain: "switch", service: "turn_on", entityId: "switch.deye_solar_sell" },
  ]);
});

test("ne commande jamais un interrupteur non identifié comme injection", () => {
  assert.deepEqual(gridExportReleaseCommands([
    { entityId: "switch.filtration", name: "Filtration piscine" },
  ]), []);
});
