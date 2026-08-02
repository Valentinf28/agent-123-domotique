import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_SOLAR_INSTALLED_POWER_WP,
  normalizeEnabledModules,
  normalizeSolarInstalledPowerWp,
} from "../lib/client-modules.js";

test("conserve Maison et applique les modules configurés dans l'ordre client", () => {
  assert.deepEqual(
    normalizeEnabledModules('["vehicle","solar","unknown"]'),
    ["home", "solar", "vehicle"],
  );
  assert.deepEqual(normalizeEnabledModules(["pool"]), ["home", "pool"]);
  assert.deepEqual(normalizeEnabledModules("invalide"), ["home"]);
});

test("transmet la puissance solaire installée avec un repli positif", () => {
  assert.equal(normalizeSolarInstalledPowerWp(12_400), 12_400);
  assert.equal(normalizeSolarInstalledPowerWp("5810.4"), 5_810);
  assert.equal(normalizeSolarInstalledPowerWp(0), DEFAULT_SOLAR_INSTALLED_POWER_WP);
  assert.equal(normalizeSolarInstalledPowerWp(null), DEFAULT_SOLAR_INSTALLED_POWER_WP);
});
