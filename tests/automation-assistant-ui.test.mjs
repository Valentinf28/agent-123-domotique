import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const portal = fs.readFileSync(new URL("../app/portal.tsx", import.meta.url), "utf8");
const proposeRoute = fs.readFileSync(new URL("../app/api/assistant/automation/propose/route.ts", import.meta.url), "utf8");
const confirmRoute = fs.readFileSync(new URL("../app/api/assistant/automation/confirm/route.ts", import.meta.url), "utf8");

test("impose un aperçu et une confirmation séparée avant toute création", () => {
  assert.match(portal, /APERÇU À CONFIRMER · NON ACTIVÉ/);
  assert.match(portal, /Confirmer et créer/);
  assert.match(portal, /confirmed: true/);
  assert.match(confirmRoute, /EXPLICIT_CONFIRMATION_REQUIRED/);
  assert.match(confirmRoute, /verifyAutomationProposal/);
});

test("propose la documentation puis le support en dernier recours", () => {
  assert.match(portal, /Créer un ticket support/);
  assert.match(portal, /Vérifiez que l’appareil est en ligne/);
  assert.match(proposeRoute, /consumeAssistantRequest/);
  assert.match(proposeRoute, /PREMIUM_REQUIRED/);
});
