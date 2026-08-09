export type CoachAutomationProposal = {
  name: string;
  trigger: string;
  action: string;
  rationale: string;
};

export function executableCoachProposal(proposal: CoachAutomationProposal | null) {
  if (!proposal) return null;
  const trigger = proposal.trigger.trim();
  const action = proposal.action.trim();
  const fullProposal = `${proposal.name} ${trigger} ${action} ${proposal.rationale}`;
  const hasSupportedTrigger = /\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]\d\b/i.test(trigger) ||
    /\b(?:lever|coucher)\s+(?:du\s+)?soleil\b/i.test(trigger);
  const hasConcreteAction = /(?:^|\s)(?:allum|étein|etein|active|désactive|desactive|ouvre|ferme|démarre|demarre|arrête|arrete|coupe)\S*/i.test(action);
  const turnsDynamicAdviceIntoFixedSchedule = /surplus|batterie|m[ée]t[ée]o|pr[ée]vision|tarif|heures?\s+creuses?|production\s+solaire|au\s+solaire/i.test(fullProposal) &&
    !/\b(?:lever|coucher)\s+(?:du\s+)?soleil\b/i.test(trigger);
  return hasSupportedTrigger && hasConcreteAction && !turnsDynamicAdviceIntoFixedSchedule
    ? proposal
    : null;
}

export function safeCoachSuggestedQuestions(questions: string[]) {
  return questions.filter((question) => {
    const fixedTime = /\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]?\d?\b/i.test(question);
    const asksAutomation = /automati|programme|planifie|d[ée]cale|cr[ée]e?\s+(?:une\s+)?r[èe]gle/i.test(question);
    const dynamicEnergy = /solaire|surplus|batterie|m[ée]t[ée]o|pr[ée]vision|demain/i.test(question);
    const ambiguousChoice = /^(?:souhaitez-vous|voulez-vous|est-ce que vous voulez|dois-je)\b/i.test(question.trim());
    return !(asksAutomation && fixedTime && dynamicEnergy) && !ambiguousChoice;
  }).slice(0, 3);
}
