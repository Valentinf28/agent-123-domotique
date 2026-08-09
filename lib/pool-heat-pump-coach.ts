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

  const weatherFixedSchedule = /(?:demain|météo|meteo|fera\s+beau|prévision|prevision)/.test(normalized) &&
    /(?:programme|planifie|démarre|demarre|allume)/.test(normalized) &&
    /\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]?\d?\b/.test(normalized);
  if (weatherFixedSchedule) return {
    answer: "Je ne transforme pas la météo ponctuelle de demain en règle horaire répétée : elle pourrait démarrer la PAC un jour nuageux et solliciter le réseau ou la batterie. Utilisez le pilotage énergétique qui vérifie le surplus réel, ou demandez une programmation exceptionnelle clairement limitée à demain.",
    automationProposal: null,
    suggestedQuestions: ["Quel est le meilleur créneau solaire demain ?", "Arrêter la PAC piscine au coucher du soleil", "Quelle température cible conserver ?"],
  };

  const afterSolar = /(?:après|apres)[^.!?]{0,45}(?:solaire|production)[^.!?]{0,30}(?:arrêt|arret|stopp|termin|fini)/.test(normalized)
    || /(?:après|apres)[^.!?]{0,20}(?:arrêt|arret|stopp|fin)[^.!?]{0,35}(?:solaire|production)/.test(normalized)
    || /(?:plus|pas)\s+de\s+production\s+solaire/.test(normalized);
  const batteryImpact = /(?:vid|décharg|decharg|tir|sollicit|puis)[^.!?]{0,35}(?:la\s+)?batterie/.test(normalized)
    || /batterie[^.!?]{0,35}(?:vid|décharg|decharg|tir|sollicit)/.test(normalized);
  const unnecessary = /(?:pas|aucun)\s+d['’]?intérêt|inutile|serv(?:ait|i)\s+à\s+rien|trop\s+longtemps|sans\s+bénéfice/.test(normalized);
  const temperature = statedWaterTemperature(message);
  const strongScenario = afterSolar && batteryImpact && (unnecessary || temperature != null);
  const asksWhyAfterSunset = /pourquoi/.test(normalized) && /(?:coucher\s+du\s+soleil|après|apres).{0,35}(?:soleil|solaire)|(?:après|apres).{0,35}(?:coucher\s+du\s+soleil|solaire)/.test(normalized);
  if (!strongScenario && !asksWhyAfterSunset) return null;

  const statedFact = temperature == null
    ? asksWhyAfterSunset
      ? "Vous indiquez que la PAC a continué après le coucher du soleil. Les mesures actuelles ne permettent pas d’identifier rétrospectivement la cause, la température de l’eau ni la consigne à cet instant."
      : "Vous indiquez que la PAC a continué sans bénéfice utile après l’arrêt du solaire."
    : `Vous indiquez que l’eau était déjà à ${String(temperature).replace('.', ',')} °C et que la PAC a continué après l’arrêt du solaire.`;
  return {
    answer: [
      `${statedFact}${asksWhyAfterSunset && temperature == null ? "" : " Dans ce cas, elle a sollicité la batterie inutilement d’après votre constat."}`,
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
