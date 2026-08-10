export type CoachQuestionIntent = 'money' | 'battery' | 'solar' | 'vehicle' | 'hot-water' | 'general';

export function coachQuestionIntent(message: string): CoachQuestionIntent {
  const normalized = message.toLocaleLowerCase('fr-FR');
  if (/facture|prix|tarif|co[uû]t|euros?|heures?\s+creuses?|heures?\s+pleines?|mensuel|ce\s+mois|combien.{0,20}(?:gagner|économiser)|vendre.{0,20}surplus/.test(normalized)) return 'money';
  if (/batterie|soc\b|réserve|reserve|autonomie/.test(normalized)) return 'battery';
  if (/voiture|tesla|véhicule|vehicule|recharge|borne/.test(normalized)) return 'vehicle';
  if (/solaire|surplus|autoconsomm|photovolta/.test(normalized)) return 'solar';
  if (/chauffe[- ]?eau|ballon|eau\s+chaude/.test(normalized)) return 'hot-water';
  if (/\b(?:économiser|economiser|économies|economies|bilan)\b/.test(normalized)) return 'money';
  return 'general';
}

export function needsDeterministicFinancialAnswer(message: string) {
  return coachQuestionIntent(message) === 'money';
}

export function asksForCoachActionPlan(message: string) {
  const normalized = message.toLowerCase();
  return /(?:plan|priorit[ée]s?|recommandations?|actions?)/.test(normalized) &&
    /(?:14\s*jours|deux\s+semaines|analyse|prochain|propose|conseille|faire)/.test(normalized);
}

export function asksForBatteryEndurance(message: string) {
  const normalized = message.toLowerCase();
  return /batterie|réserve|reserve|autonomie/.test(normalized) &&
    /(?:tenir|autonomie|jusqu|toute\s+la\s+nuit|passer\s+la\s+nuit|combien\s+d['’]?heures?|combien.{0,20}énergie|énergie.{0,20}avant)/.test(normalized);
}

export function asksForHouseStatus(message: string) {
  const normalized = message.toLowerCase();
  return /(?:que se passe|consomment? le plus|consommation actuelle|anomalie énergétique|consomme.{0,15}la nuit|sait réellement|données.{0,15}manquent|premier changement|équipements?.{0,20}pilotables?)/.test(normalized);
}

export function asksForFiltrationBatteryProtection(message: string) {
  const normalized = message.toLocaleLowerCase('fr-FR');
  return /filtration/.test(normalized) && /batterie/.test(normalized) &&
    /solaire|production|réseau|reseau|météo|meteo|temps/.test(normalized);
}

export function asksForCurrentWeekCost(message: string) {
  const normalized = message.toLocaleLowerCase('fr-FR');
  return /(?:combien|quel montant).{0,35}d[ée]pens[ée].{0,35}(?:depuis (?:le )?d[ée]but de la semaine|cette semaine)|d[ée]pens[ée].{0,35}(?:depuis (?:le )?d[ée]but de la semaine|cette semaine)/.test(normalized);
}
