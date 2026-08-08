export type PoolHeatPumpCoachReply = {
  answer: string;
  automationProposal: {
    name: string;
    trigger: string;
    action: string;
    rationale: string;
  } | null;
  suggestedQuestions: string[];
};

function statedWaterTemperature(message: string) {
  const match = message.match(/(?:eau|piscine)?[^.!?]{0,24}(?:à|a|était|etait)\s*(\d{1,2}(?:[,.]\d)?)\s*°?\s*c?\b/i);
  if (!match) return null;
  const value = Number(match[1].replace(',', '.'));
  return Number.isFinite(value) && value >= 5 && value <= 45 ? value : null;
}

export function poolHeatPumpCoachReply(message: string): PoolHeatPumpCoachReply | null {
  const normalized = message.toLocaleLowerCase('fr-FR');
  const mentionsHeatPump = /\bpac\b|pompe\s+à\s+chaleur/.test(normalized);
  if (!mentionsHeatPump) return null;

  const afterSolar = /(?:après|apres)[^.!?]{0,45}(?:solaire|production)[^.!?]{0,30}(?:arrêt|arret|stopp|termin|fini)/.test(normalized)
    || /(?:après|apres)[^.!?]{0,20}(?:arrêt|arret|stopp|fin)[^.!?]{0,35}(?:solaire|production)/.test(normalized)
    || /(?:plus|pas)\s+de\s+production\s+solaire/.test(normalized);
  const batteryImpact = /(?:vid|décharg|decharg|tir|sollicit|puis)[^.!?]{0,35}(?:la\s+)?batterie/.test(normalized)
    || /batterie[^.!?]{0,35}(?:vid|décharg|decharg|tir|sollicit)/.test(normalized);
  const unnecessary = /(?:pas|aucun)\s+d['’]?intérêt|inutile|serv(?:ait|i)\s+à\s+rien|trop\s+longtemps|sans\s+bénéfice/.test(normalized);
  const temperature = statedWaterTemperature(message);
  const strongScenario = afterSolar && batteryImpact && (unnecessary || temperature != null);
  if (!strongScenario) return null;

  const statedFact = temperature == null
    ? "Vous indiquez que la PAC a continué sans bénéfice utile après l’arrêt du solaire."
    : `Vous indiquez que l’eau était déjà à ${String(temperature).replace('.', ',')} °C et que la PAC a continué après l’arrêt du solaire.`;
  return {
    answer: [
      `${statedFact} Dans ce cas, elle a sollicité la batterie inutilement d’après votre constat.`,
      "Je propose une coupure de sécurité au coucher du soleil. Le chauffage pourra reprendre en journée si l’eau est sous la consigne.",
      "Règle suggérée : au coucher du soleil, éteindre la PAC piscine.",
    ].join(' '),
    automationProposal: {
      name: "Arrêt nocturne de la PAC piscine",
      trigger: "Au coucher du soleil",
      action: "Éteindre la PAC piscine",
      rationale: "Éviter de solliciter la batterie lorsque le chauffage de la piscine n’est plus utile le soir.",
    },
    suggestedQuestions: [
      "À quelle heure relancer la PAC demain ?",
      "Quelle réserve batterie conserver le soir ?",
      "Comment éviter une surchauffe de la piscine ?",
    ],
  };
}
