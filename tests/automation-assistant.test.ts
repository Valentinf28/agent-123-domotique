import assert from "node:assert/strict";
import test from "node:test";
import {
  proposeSafeAutomation,
  signAutomationProposal,
  verifyAutomationProposal,
  type AssistantDevice,
} from "../lib/automation-assistant";

const devices: AssistantDevice[] = [
  { publicId: "filtration", name: "Filtration", room: "Piscine", category: "Piscine", available: true, controllable: true },
  { publicId: "pac", name: "PAC piscine", room: "Piscine", category: "Piscine", available: true, controllable: true },
  { publicId: "ballon", name: "Ballon d’eau chaude", room: "Local technique", category: "Eau chaude", available: true, controllable: true },
  { publicId: "portail", name: "Portail", room: "Extérieur", category: "Accès", available: true, controllable: true },
];

test("prépare une règle quotidienne sûre à partir d’une phrase française", () => {
  const result = proposeSafeAutomation("Allume la filtration tous les jours à 10h30", devices);
  assert.equal(result.status, "ready");
  if (result.status !== "ready") return;
  assert.equal(result.proposal.time, "10:30");
  assert.equal(result.proposal.triggerType, "time");
  assert.equal(result.proposal.publicDeviceId, "filtration");
  assert.equal(result.proposal.desiredActive, true);
});

test("comprend les jours de semaine et le coucher du soleil", () => {
  const result = proposeSafeAutomation("Allume la lumière piscine au coucher du soleil le week-end", [
    ...devices,
    { publicId: "pool-light", name: "Lumière piscine", room: "Piscine", category: "Piscine", available: true, controllable: true },
  ]);
  assert.equal(result.status, "ready");
  if (result.status !== "ready") return;
  assert.equal(result.proposal.triggerType, "sunset");
  assert.equal(result.proposal.time, null);
  assert.deepEqual(result.proposal.weekdays, ["sat", "sun"]);
  assert.match(result.proposal.triggerLabel, /week-end.*coucher du soleil/i);
});

test("comprend une règle limitée aux jours ouvrables", () => {
  const result = proposeSafeAutomation("Allume le ballon d'eau chaude en semaine à 12h30", devices);
  assert.equal(result.status, "ready");
  if (result.status !== "ready") return;
  assert.deepEqual(result.proposal.weekdays, ["mon", "tue", "wed", "thu", "fri"]);
  assert.equal(result.proposal.time, "12:30");
});
test("comprend midi, l’arrêt et le ballon d’eau chaude", () => {
  const result = proposeSafeAutomation("Coupe le ballon d'eau chaude à midi", devices);
  assert.equal(result.status, "ready");
  if (result.status !== "ready") return;
  assert.equal(result.proposal.time, "12:00");
  assert.equal(result.proposal.publicDeviceId, "ballon");
  assert.equal(result.proposal.desiredActive, false);
});

test("demande une précision lorsque piscine est ambigu", () => {
  assert.equal(proposeSafeAutomation("Allume la piscine à 9h", devices).status, "needs_clarification");
});

test("refuse les actions dangereuses et les accès sensibles", () => {
  assert.equal(proposeSafeAutomation("Ouvre le portail tous les jours à 8h", devices).status, "refused");
  assert.equal(proposeSafeAutomation("Désactive l'alarme à 23h", devices).status, "refused");
});

test("ne propose jamais un appareil indisponible", () => {
  const unavailable = devices.map((device) => device.publicId === "filtration" ? { ...device, available: false } : device);
  assert.equal(proposeSafeAutomation("Allume la filtration à 10h", unavailable).status, "needs_clarification");
});

test("le jeton d’aperçu est signé, limité dans le temps et lié à la maison", async () => {
  const result = proposeSafeAutomation("Allume la PAC piscine à 11h", devices);
  assert.equal(result.status, "ready");
  if (result.status !== "ready") return;
  const token = await signAutomationProposal(result.proposal, "maison-1", "secret-de-test", 1_000);
  const payload = await verifyAutomationProposal(token, "secret-de-test", 2_000);
  assert.equal(payload?.dossierPublicId, "maison-1");
  assert.equal(payload?.rule.publicDeviceId, "pac");
  assert.equal(await verifyAutomationProposal(`${token}x`, "secret-de-test", 2_000), null);
  assert.equal(await verifyAutomationProposal(token, "secret-de-test", 1_000 + 10 * 60 * 1000 + 1), null);
});
