import assert from "node:assert/strict";
import test from "node:test";
import { buildBatteryNightOutlook } from "../lib/battery-night-outlook";

function historyWithNightProfile(wattsByHour: (hour: number) => number) {
  return Array.from({ length: 10 * 24 * 6 }, (_, index) => {
    const capturedAt = new Date(Date.UTC(2026, 6, 20, 0, index * 10));
    return {
      capturedAt: capturedAt.toISOString(),
      batteryWatts: wattsByHour(capturedAt.getUTCHours()),
      solarWatts: capturedAt.getUTCHours() >= 7 && capturedAt.getUTCHours() < 19 ? 2500 : 0,
    };
  });
}

test("ne prolonge pas la filtration instantanée sur toute la nuit", () => {
  const result = buildBatteryNightOutlook({
    now: new Date("2026-08-09T00:00:00.000Z"),
    batteryCapacityWh: 15_000,
    batteryPercent: 49,
    reservePercent: 25,
    currentDischargeWatts: 1_210,
    nextSolarAt: "2026-08-09T05:30:00.000Z",
    history: historyWithNightProfile((hour) => hour < 1 ? 1200 : 450),
  });
  assert.equal(result.holdsUntilSolar, true);
  assert.ok(result.expectedWh < result.usableWh);
  assert.equal(result.confidence, "measured");
});

test("signale honnêtement une autonomie insuffisante selon le profil habituel", () => {
  const result = buildBatteryNightOutlook({
    now: new Date("2026-08-09T00:00:00.000Z"),
    batteryCapacityWh: 10_000,
    batteryPercent: 40,
    reservePercent: 25,
    currentDischargeWatts: 900,
    nextSolarAt: "2026-08-09T06:00:00.000Z",
    history: historyWithNightProfile(() => 900),
  });
  assert.equal(result.holdsUntilSolar, false);
  assert.ok(result.expectedWh > result.usableWh);
});

test("refuse de conclure si la capacité n’est pas configurée", () => {
  const result = buildBatteryNightOutlook({
    now: new Date("2026-08-09T00:00:00.000Z"),
    batteryCapacityWh: 0,
    batteryPercent: 49,
    reservePercent: 25,
    currentDischargeWatts: 1_210,
    history: [],
  });
  assert.equal(result.available, false);
  assert.equal(result.holdsUntilSolar, null);
});
