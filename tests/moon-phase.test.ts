import assert from "node:assert/strict";
import test from "node:test";
import {
  moonDisplayPhase,
  moonIlluminationForDate,
  moonPhaseForDate,
  normalizeMoonPhase,
} from "../lib/moon-phase.ts";

test("normalise les états Home Assistant en français", () => {
  assert.equal(normalizeMoonPhase("Pleine lune"), "full_moon");
  assert.equal(normalizeMoonPhase("Gibbeuse décroissante"), "waning_gibbous");
});

test("calcule une phase lorsque le capteur Home Assistant manque", () => {
  assert.equal(moonPhaseForDate(new Date("2000-01-06T18:14:00Z")), "new_moon");
  assert.equal(moonPhaseForDate(new Date("2000-01-21T12:36:00Z")), "full_moon");
});

test("conserve une pleine lune visuelle autour du maximum d'illumination", () => {
  const date = new Date("2000-01-21T12:36:00Z");
  assert.ok(moonIlluminationForDate(date) > 0.9);
  assert.equal(moonDisplayPhase("waning_gibbous", date), "full_moon");
});
