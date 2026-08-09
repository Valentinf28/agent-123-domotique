import assert from "node:assert/strict";
import test from "node:test";
import { coachQAScenarios, coachQATurnCount } from "../scripts/coach-qa-scenarios.ts";
import { evaluateCoachAnswer } from "../scripts/coach-qa-agent.ts";

test("le corpus QA contient au moins cinquante questions et des dialogues multi-tours", () => {
  assert.ok(coachQATurnCount >= 50);
  assert.ok(coachQAScenarios.every((scenario) => scenario.turns.length >= 2));
});

test("l’agent détecte une réponse hors sujet ou mensongère", () => {
  const errors = evaluateCoachAnswer("Oui, j’ai activé la PAC piscine.", {
    require: [/filtration/i],
    forbid: [/PAC piscine/i, /j['’]ai activé/i],
    maxWords: 20,
  });
  assert.equal(errors.length, 3);
});

test("l’agent accepte une réponse concise qui contient les faits attendus", () => {
  assert.deepEqual(evaluateCoachAnswer(
    "La filtration sera mise en pause à 20 %, puis relancée lorsque le surplus réel sera suffisant.",
    { require: [/filtration/i, /20\s*%/, /surplus réel/i], forbid: [/PAC piscine/i], maxWords: 30 },
  ), []);
});
