import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { coachQAScenarios, coachQATurnCount, type QARule } from "./coach-qa-scenarios.ts";

type ChatMessage = { role: "client" | "coach"; text: string };
type Finding = { scenario: string; theme: string; question: string; answer: string; errors: string[] };

const checkOnly = process.argv.includes("--check");
const endpoint = process.env.COACH_QA_ENDPOINT?.trim();
const dossierPublicId = process.env.COACH_QA_DOSSIER_ID?.trim();
const cookie = process.env.COACH_QA_COOKIE?.trim();

function words(value: string) {
  return value.trim().split(/\s+/).filter(Boolean).length;
}

export function evaluateCoachAnswer(answer: string, rule: QARule) {
  const errors: string[] = [];
  for (const expected of rule.require ?? []) {
    if (!expected.test(answer)) errors.push(`Information attendue absente : ${expected}`);
  }
  for (const forbidden of rule.forbid ?? []) {
    if (forbidden.test(answer)) errors.push(`Affirmation interdite détectée : ${forbidden}`);
  }
  if (rule.maxWords && words(answer) > rule.maxWords) {
    errors.push(`Réponse trop longue : ${words(answer)} mots (maximum ${rule.maxWords})`);
  }
  return errors;
}

async function askCoach(message: string, conversation: ChatMessage[]) {
  if (!endpoint || !dossierPublicId) throw new Error("Configuration QA incomplète");
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: JSON.stringify({ message, dossierPublicId, conversation: conversation.slice(-6) }),
  });
  const payload = await response.json() as { reply?: { answer?: string }; error?: string };
  if (!response.ok || !payload.reply?.answer) {
    throw new Error(`Coach HTTP ${response.status}: ${payload.error ?? "réponse vide"}`);
  }
  return payload.reply.answer;
}

function markdown(findings: Finding[], tested: number) {
  const failed = findings.length;
  const lines = [
    "# Rapport de l’agent QA du Coach",
    "",
    `- Questions et relances testées : ${tested}`,
    `- Réponses conformes : ${tested - failed}`,
    `- Réponses à corriger : ${failed}`,
    `- Résultat : ${failed === 0 ? "VALIDÉ" : "ÉCHEC"}`,
    "",
  ];
  for (const finding of findings) {
    lines.push(`## ${finding.scenario} — ${finding.theme}`, "", `**Client :** ${finding.question}`, "", `**Coach :** ${finding.answer}`, "", "**Problèmes :**", ...finding.errors.map((error) => `- ${error}`), "");
  }
  return lines.join("\n");
}

async function main() {
  if (checkOnly) {
    if (coachQATurnCount < 30) throw new Error(`Corpus trop petit : ${coachQATurnCount} tours`);
    for (const scenario of coachQAScenarios) {
      if (!scenario.id || scenario.turns.length < 2) throw new Error(`Scénario invalide : ${scenario.id}`);
      for (const turn of scenario.turns) {
        if (!turn.rule.require?.length) throw new Error(`Critère positif absent : ${scenario.id}`);
      }
    }
    console.log(`Agent QA prêt : ${coachQAScenarios.length} scénarios, ${coachQATurnCount} questions et relances.`);
    return;
  }
  if (!endpoint || !dossierPublicId) {
    throw new Error("Définissez COACH_QA_ENDPOINT et COACH_QA_DOSSIER_ID. Ajoutez COACH_QA_COOKIE pour une production authentifiée.");
  }
  const findings: Finding[] = [];
  let tested = 0;
  for (const scenario of coachQAScenarios) {
    const conversation: ChatMessage[] = [];
    for (const turn of scenario.turns) {
      const answer = await askCoach(turn.message, conversation);
      tested += 1;
      const errors = evaluateCoachAnswer(answer, turn.rule);
      if (errors.length) findings.push({ scenario: scenario.id, theme: scenario.theme, question: turn.message, answer, errors });
      conversation.push({ role: "client", text: turn.message }, { role: "coach", text: answer });
    }
  }
  const outputDir = resolve("artifacts/coach-evals");
  await mkdir(outputDir, { recursive: true });
  await Promise.all([
    writeFile(resolve(outputDir, "latest.json"), JSON.stringify({ tested, failed: findings.length, findings }, null, 2)),
    writeFile(resolve(outputDir, "latest.md"), markdown(findings, tested)),
  ]);
  console.log(`Agent QA : ${tested - findings.length}/${tested} réponses conformes. Rapport : artifacts/coach-evals/latest.md`);
  if (findings.length) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
