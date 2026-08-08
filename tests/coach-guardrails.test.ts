import assert from "node:assert/strict";
import test from "node:test";
import { executableCoachProposal } from "../lib/coach-guardrails.ts";

test("accepte une automatisation simple et explicitement horaire", () => {
  const proposal = {
    name: "Éclairage terrasse",
    trigger: "Tous les jours à 23:30",
    action: "Éteindre la terrasse",
    rationale: "Éviter un éclairage oublié la nuit.",
  };
  assert.deepEqual(executableCoachProposal(proposal), proposal);
});

test("refuse de figer la prévision solaire du jour dans une règle quotidienne", () => {
  assert.equal(executableCoachProposal({
    name: "Démarrer la PAC piscine au solaire",
    trigger: "À 12:00",
    action: "Démarrer la PAC piscine",
    rationale: "Profiter de la production solaire prévue aujourd’hui.",
  }), null);
});

test("refuse une règle fixe prétendument pilotée par la batterie", () => {
  assert.equal(executableCoachProposal({
    name: "Protection batterie",
    trigger: "À 21:00",
    action: "Éteindre le chauffe-eau",
    rationale: "Préserver la batterie quand elle est faible.",
  }), null);
});

test("conserve la coupure au coucher du soleil", () => {
  const proposal = {
    name: "Arrêt nocturne de la PAC piscine",
    trigger: "Au coucher du soleil",
    action: "Éteindre la PAC piscine",
    rationale: "Éviter une chauffe nocturne inutile.",
  };
  assert.deepEqual(executableCoachProposal(proposal), proposal);
});
