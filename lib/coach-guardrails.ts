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
