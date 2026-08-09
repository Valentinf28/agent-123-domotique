import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const portal = fs.readFileSync(new URL("../app/portal.tsx", import.meta.url), "utf8");
const proposeRoute = fs.readFileSync(new URL("../app/api/assistant/automation/propose/route.ts", import.meta.url), "utf8");
const confirmRoute = fs.readFileSync(new URL("../app/api/assistant/automation/confirm/route.ts", import.meta.url), "utf8");
const statusRoute = fs.readFileSync(new URL("../app/api/assistant/automation/status/route.ts", import.meta.url), "utf8");
const energyRoute = fs.readFileSync(new URL("../app/api/assistant/energy/route.ts", import.meta.url), "utf8");
const poolHeatPumpCoach = fs.readFileSync(new URL("../lib/pool-heat-pump-coach.ts", import.meta.url), "utf8");

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

test("permet à l’installateur de présenter l’assistant sans modifier le forfait client", () => {
  assert.match(proposeRoute, /portalApiAdminAuthorized/);
  assert.match(proposeRoute, /remoteAccessAllowed\s*\|\|/);
  assert.match(proposeRoute, /Activez ou renouvelez le forfait Premium/);
});

test("affiche immédiatement la règle confirmée pendant sa synchronisation", () => {
  assert.match(portal, /pendingAutomations/);
  assert.match(portal, /Synchronisation en cours/);
  assert.match(portal, /requestHomeRefresh/);
  assert.match(portal, /automation\/status/);
  assert.match(statusRoute, /agentCommands/);
  assert.match(statusRoute, /Cache-Control/);
});

test("nomme toujours la box avec la marque 1.2.3. Home", () => {
  assert.doesNotMatch(portal, /Green Box/i);
  assert.doesNotMatch(proposeRoute, /Green Box/i);
  assert.doesNotMatch(confirmRoute, /Green Box/i);
  assert.match(portal, /box 1\.2\.3\. Home/);
});

test("le coach distingue la PAC de la filtration et répond avec une action concise", () => {
  assert.match(energyRoute, /90 mots maximum/);
  assert.match(energyRoute, /Distingue toujours la filtration de la PAC piscine/);
  assert.match(energyRoute, /mesuresActuelles décrivent uniquement l’instant présent/);
  assert.match(poolHeatPumpCoach, /Arrêt nocturne de la PAC piscine/);
  assert.match(poolHeatPumpCoach, /Au coucher du soleil/);
  assert.match(portal, /conversation: coachMessages\.slice/);
  assert.match(portal, /Proposition affichée/);
  assert.match(energyRoute, /Une réponse courte comme oui, non/);
  assert.match(energyRoute, /Préparer cette proposition/);
});

test("le coach affiche un vrai bouton pour préparer la protection de la filtration", () => {
  assert.match(portal, /coach-setup-button/);
  assert.match(portal, />Préparer cette proposition</);
  assert.match(portal, /prepareAssistantAutomation\(request\)/);
});

test("le parcours d’aperçu s’ouvre automatiquement pour rendre le résultat visible", () => {
  assert.match(portal, /coach-automation-detail" open>/);
});

test("présente des exemples de règles réellement prises en charge", () => {
  assert.match(portal, /Allume la filtration en semaine à 10h30/);
  assert.match(portal, /coucher du soleil le week-end/);
  assert.match(proposeRoute, /lever\/coucher du soleil/);
});
