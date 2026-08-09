import assert from "node:assert/strict";
import test from "node:test";
import { coachConversationContinuation } from "../lib/coach-conversation.ts";

const conversation = [{
  role: "coach" as const,
  text: "Je propose une protection.\nProposition affichée : Arrêt nocturne de la PAC piscine. Quand : Au coucher du soleil. Action : Éteindre la PAC piscine. Pourquoi : Éviter de vider la batterie après la production solaire.",
}];

test("oui conserve la proposition affichée au lieu de changer de sujet", () => {
  const reply = coachConversationContinuation("oui", conversation);
  assert.match(reply?.answer ?? "", /Parfait/);
  assert.equal(reply?.automationProposal?.name, "Arrêt nocturne de la PAC piscine");
});

test("fais-le exige toujours l’aperçu avant activation", () => {
  const reply = coachConversationContinuation("fais-le", conversation);
  assert.match(reply?.answer ?? "", /Préparer cette proposition/);
  assert.doesNotMatch(reply?.answer ?? "", /activée|créée/);
});

test("non abandonne clairement la proposition", () => {
  const reply = coachConversationContinuation("non merci", conversation);
  assert.equal(reply?.automationProposal, null);
  assert.match(reply?.answer ?? "", /je ne prépare rien/i);
});

test("pourquoi explique la proposition existante", () => {
  const reply = coachConversationContinuation("pourquoi ?", conversation);
  assert.match(reply?.answer ?? "", /Éviter de vider la batterie/);
});
