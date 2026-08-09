import assert from "node:assert/strict";
import test from "node:test";
import { measuredVehicleEnergyToday } from "../lib/measured-vehicle-energy";

test("calcule les kWh réellement mesurés pour la voiture aujourd'hui", () => {
  const result = measuredVehicleEnergyToday([
    { capturedAt: "2026-08-09T10:00:00+02:00", vehicleWatts: 3_000 },
    { capturedAt: "2026-08-09T10:05:00+02:00", vehicleWatts: 3_000 },
    { capturedAt: "2026-08-09T10:10:00+02:00", vehicleWatts: 3_000 },
  ], new Date("2026-08-09T10:11:00+02:00"));

  assert.equal(result.available, true);
  assert.equal(result.energyWh, 500);
  assert.equal(result.coveredMinutes, 10);
});

test("n'extrapole pas une recharge à travers une coupure de collecte", () => {
  const result = measuredVehicleEnergyToday([
    { capturedAt: "2026-08-09T10:00:00+02:00", vehicleWatts: 7_000 },
    { capturedAt: "2026-08-09T12:00:00+02:00", vehicleWatts: 7_000 },
  ], new Date("2026-08-09T12:01:00+02:00"));

  assert.equal(result.available, false);
  assert.equal(result.energyWh, 0);
});

test("ignore les relevés d'un autre jour", () => {
  const result = measuredVehicleEnergyToday([
    { capturedAt: "2026-08-08T23:55:00+02:00", vehicleWatts: 3_000 },
    { capturedAt: "2026-08-09T00:00:00+02:00", vehicleWatts: 3_000 },
    { capturedAt: "2026-08-09T00:05:00+02:00", vehicleWatts: 3_000 },
  ], new Date("2026-08-09T00:06:00+02:00"));

  assert.equal(result.energyWh, 250);
  assert.equal(result.sampleCount, 2);
});
