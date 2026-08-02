import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const portal = readFileSync(new URL("../app/portal.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("le portail client n'invente aucun contrôle pendant une reconnexion", () => {
  assert.match(portal, /const controls = overview\?\.controls \?\? \[\];/);
  assert.doesNotMatch(portal, /demo-(?:heat|filter|pool|lock|camera|water)/);
});

test("les quatre onglets premium partagent la mise en page mobile compacte", () => {
  assert.match(portal, /compact-category-layout/);
  assert.match(css, /\.heating-mobile-section,\.vehicle-mobile-section/);
  assert.match(css, /\.pool-mobile-section\{padding-top:0\}/);
  assert.match(css, /\.equipment-premium\.mobile-section/);
});
