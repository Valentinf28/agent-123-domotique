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

test("ok vas-y poursuit le paramétrage de la filtration et demande seulement la durée manquante", () => {
  const reply = coachConversationContinuation("ok vasy", [{
    role: "coach",
    text: "Pour l’automatiser correctement, la filtration doit d’abord être déclarée comme usage flexible pilotable.",
  }]);
  assert.match(reply?.answer ?? "", /combien d’heures minimum/i);
  assert.doesNotMatch(reply?.answer ?? "", /professionnel|PAC piscine/i);
  assert.deepEqual(reply?.suggestedQuestions, []);
});

test("fais est compris comme une validation du paramétrage de filtration", () => {
  const reply = coachConversationContinuation("fais", [{
    role: "coach",
    text: "La filtration doit être configurée comme équipement pilotable et usage flexible.",
  }]);
  assert.match(reply?.answer ?? "", /une seule donnée/i);
});

test("on fait ça poursuit le paramétrage au lieu d’annoncer un bouton absent", () => {
  const reply = coachConversationContinuation("on fait ça", [{
    role: "coach",
    text: "Pour l’automatiser, la filtration doit être déclarée comme usage flexible pilotable.",
  }]);
  assert.match(reply?.answer ?? "", /combien d’heures minimum/i);
  assert.doesNotMatch(reply?.answer ?? "", /Préparer cette proposition/i);
});

for (const approval of ["ok fais ça stp", "vas-y alors", "oui fais-le stp"]) {
  test(`comprend la validation naturelle « ${approval} »`, () => {
    const reply = coachConversationContinuation(approval, [{
      role: "coach",
      text: "La filtration doit être déclarée comme usage flexible pilotable.",
    }]);
    assert.match(reply?.answer ?? "", /combien d’heures minimum/i);
  });
}
