export type CoachConversationMessage = { role: "client" | "coach"; text: string };

export type CoachConversationReply = {
  answer: string;
  automationProposal: {
    name: string;
    trigger: string;
    action: string;
    rationale: string;
  } | null;
  suggestedQuestions: string[];
};

function displayedProposal(conversation: CoachConversationMessage[]) {
  const lastCoach = [...conversation].reverse().find((item) => item.role === "coach");
  if (!lastCoach) return null;
  const match = lastCoach.text.match(/Proposition affichée\s*:\s*(.+?)\. Quand\s*:\s*(.+?)\. Action\s*:\s*(.+?)\. Pourquoi\s*:\s*(.+?)(?:\.|$)/s);
  if (!match) return null;
  return {
    name: match[1].trim(),
    trigger: match[2].trim(),
    action: match[3].trim(),
    rationale: match[4].trim(),
  };
}

export function coachConversationContinuation(
  message: string,
  conversation: CoachConversationMessage[],
): CoachConversationReply | null {
  const normalized = message.toLocaleLowerCase("fr-FR").trim().replace(/[.!?]+$/g, "").trim();
  const lastCoach = [...conversation].reverse().find((item) => item.role === "coach")?.text ?? "";
  const affirmative = /^(?:oui|ok|ok\s+vas-?y|d['’]?accord|vas-y|vasy|fais|fais-le|fait le|on\s+(?:fait|fais)\s+(?:ça|ca)|allons-y|c['’]?est parti|prépare(?:-la)?|prepare(?:-la)?)$/.test(normalized);

  if (affirmative && /filtration.{0,120}(?:usage flexible|pilotable)|(?:usage flexible|pilotable).{0,120}filtration/is.test(lastCoach)) {
    return {
      answer: "D’accord. Pour préparer correctement le pilotage de la filtration, il me manque une seule donnée que je ne dois pas inventer : combien d’heures minimum la filtration doit-elle fonctionner chaque jour ?",
      automationProposal: null,
      suggestedQuestions: [],
    };
  }
  const proposal = displayedProposal(conversation);
  if (!proposal) return null;

  if (affirmative) {
    return {
      answer: `Parfait. La règle « ${proposal.name} » est prête : ${proposal.trigger.toLocaleLowerCase("fr-FR")}, ${proposal.action.toLocaleLowerCase("fr-FR")}. Cliquez sur « Préparer cette proposition » pour vérifier l’aperçu avant de l’activer.`,
      automationProposal: proposal,
      suggestedQuestions: ["Pourquoi cette règle est-elle utile ?", "Quel sera son effet sur la batterie ?"],
    };
  }

  if (/^(?:non|non merci|pas maintenant|annule|laisse tomber)$/.test(normalized)) {
    return {
      answer: "D’accord, je ne prépare rien. La maison conserve son fonctionnement actuel.",
      automationProposal: null,
      suggestedQuestions: ["Quelle autre optimisation serait plus rentable ?", "Comment préserver la batterie sans automatisation ?"],
    };
  }

  if (/^(?:pourquoi|explique|explique-moi|quel intérêt|quel interet)$/.test(normalized)) {
    return {
      answer: `${proposal.rationale}. La règle reste un simple brouillon tant que vous n’avez pas vérifié puis confirmé son aperçu.`,
      automationProposal: proposal,
      suggestedQuestions: ["Quel sera son effet sur la batterie ?", "Préparer cette proposition"],
    };
  }

  return null;
}
