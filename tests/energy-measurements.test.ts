import assert from "node:assert/strict";
import test from "node:test";
import { energyWh, powerWatts } from "../lib/energy-measurements.ts";

test("convertit les puissances Home Assistant sans confondre W et kW", () => {
  assert.equal(powerWatts({ state: "684", unit: "W" }), 684);
  assert.equal(powerWatts({ state: "1.72", unit: "kW" }), 1_720);
  assert.equal(powerWatts({ state: "unavailable", unit: "kW" }), null);
});

test("convertit les cumuls Home Assistant sans multiplier deux fois les Wh", () => {
  assert.equal(energyWh({ state: "8400", unit: "Wh" }), 8_400);
  assert.equal(energyWh({ state: "8.4", unit: "kWh" }), 8_400);
  assert.equal(energyWh({ state: "unknown", unit: "kWh" }), null);
});
