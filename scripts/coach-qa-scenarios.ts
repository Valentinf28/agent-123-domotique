export type QARule = {
  require?: RegExp[];
  forbid?: RegExp[];
  maxWords?: number;
};

export type QATurn = {
  message: string;
  rule: QARule;
};

export type QAScenario = {
  id: string;
  theme: string;
  turns: QATurn[];
};

const never: RegExp[] = [
  /green box/i,
  /home assistant/i,
  /(?:j['’]ai|nous avons) (?:créé|activé|appliqué|modifié)/i,
];

const rule = (value: QARule): QARule => ({
  maxWords: 110,
  forbid: [...never, ...(value.forbid ?? [])],
  ...value,
});

export const coachQAScenarios: QAScenario[] = [
  {
    id: "battery-night-20kwh",
    theme: "Batterie et calculs",
    turns: [
      { message: "La batterie va tenir toute la nuit avec cette consommation ?", rule: rule({ require: [/20\s*kWh/i, /15\s*%/, /(?:oui|non|marge|jusqu)/i], forbid: [/24\s*h/i] }) },
      { message: "Combien il me reste avant le seuil ?", rule: rule({ require: [/kWh/i, /15\s*%/], forbid: [/ne connais pas.*capacit/i] }) },
      { message: "Et en heures, ça donne quoi ?", rule: rule({ require: [/(?:heure|\sh\b)/i, /15\s*%/] }) },
    ],
  },
  {
    id: "filtration-bad-weather",
    theme: "Filtration, météo et batterie",
    turns: [
      { message: "La batterie a dû faire un appoint réseau à 15 %. La filtration aurait dû s'arrêter car il n'y avait pas assez de solaire. Tu proposes quoi ?", rule: rule({ require: [/filtration/i, /20\s*%/, /surplus réel/i, /durée quotidienne/i], forbid: [/PAC piscine est/i, /heure fixe/i, /professionnel/i] }) },
      { message: "ok vas-y", rule: rule({ require: [/combien d['’]heures minimum/i], forbid: [/professionnel/i, /PAC piscine/i, /je ne peux pas/i] }) },
      { message: "6 heures minimum", rule: rule({ require: [/6\s*heures/i, /filtration/i, /(?:aperçu|proposition|préparer)/i], forbid: [/PAC piscine/i] }) },
      { message: "fais", rule: rule({ require: [/(?:aperçu|préparer|confirmation)/i], forbid: [/(?:créée|activée|appliquée)/i] }) },
    ],
  },
  {
    id: "pool-pac-past-event",
    theme: "PAC piscine et fait passé",
    turns: [
      { message: "La PAC piscine a tourné après le solaire alors que l'eau était déjà à 32 degrés. Comment éviter ça ?", rule: rule({ require: [/PAC piscine/i, /coucher du soleil/i], forbid: [/filtration représente/i, /mesure actuelle prouve/i] }) },
      { message: "oui", rule: rule({ require: [/(?:prête|aperçu|préparer)/i], forbid: [/(?:activée|appliquée)/i] }) },
      { message: "pourquoi ?", rule: rule({ require: [/(?:batterie|solaire)/i], forbid: [/nouveau conseil/i] }) },
      { message: "non merci", rule: rule({ require: [/ne prépare rien|fonctionnement actuel/i] }) },
    ],
  },
  {
    id: "solar-priority",
    theme: "Autoconsommation solaire",
    turns: [
      { message: "Comment augmenter mon autoconsommation ?", rule: rule({ require: [/(?:surplus|injection)/i, /(?:appareil|usage)/i], forbid: [/démarrez maintenant/i] }) },
      { message: "Quel appareil en premier ?", rule: rule({ require: [/(?:configuré|pilotable|surplus)/i], forbid: [/appareil absent/i] }) },
      { message: "Programme-le tous les jours à 14 h parce qu'il fera beau demain", rule: rule({ require: [/(?:prévision|météo|surplus réel|heure fixe)/i], forbid: [/règle.*14\s*h.*prête/i] }) },
    ],
  },
  {
    id: "tariff-hphc",
    theme: "Contrat et économies",
    turns: [
      { message: "Mes heures pleines/heures creuses sont-elles adaptées ?", rule: rule({ require: [/(?:achats réseau|heures creuses|heures pleines)/i], forbid: [/tarif non renseigné/i] }) },
      { message: "Je dois tout déplacer la nuit alors ?", rule: rule({ require: [/solaire/i, /heures creuses/i], forbid: [/oui,? tout/i] }) },
      { message: "Combien je gagne en euros ?", rule: rule({ require: [/€|euros?/i, /(?:estim|mesur|observ)/i], forbid: [/garanti/i] }) },
    ],
  },
  {
    id: "vehicle-surplus",
    theme: "Recharge du véhicule",
    turns: [
      { message: "Quand recharger la voiture demain ?", rule: rule({ require: [/(?:demain|prévision|surplus)/i], forbid: [/PAC piscine/i] }) },
      { message: "Crée une règle uniquement avec le surplus solaire", rule: rule({ require: [/surplus/i, /(?:pas d['’]heure fixe|mode Surplus|injection)/i], forbid: [/PAC piscine/i] }) },
      { message: "Elle doit être prête à 7 h", rule: rule({ require: [/7\s*h/i, /(?:heures creuses|repli|besoin)/i], forbid: [/garanti sans/i] }) },
    ],
  },
  {
    id: "missing-data",
    theme: "Données manquantes",
    turns: [
      { message: "Quelles données te manquent pour être précis ?", rule: rule({ require: [/(?:manque|non détaillé|identifier)/i], forbid: [/je sais tout/i] }) },
      { message: "Est-ce que mon congélateur consomme trop ?", rule: rule({ require: [/(?:mesure|donnée|identifier|pince)/i], forbid: [/oui, il consomme/i] }) },
    ],
  },
  {
    id: "action-plan",
    theme: "Plan après deux semaines",
    turns: [
      { message: "Après deux semaines, propose-moi un plan d'action concret", rule: rule({ require: [/(?:priorité|action|jours)/i], forbid: [/attendre un mois/i] }) },
      { message: "Quelle est la première action ?", rule: rule({ require: [/(?:1|premi|priorité)/i], forbid: [/trois nouveaux sujets/i] }) },
    ],
  },
  {
    id: "context-correction",
    theme: "Compréhension du dialogue",
    turns: [
      { message: "Pourquoi la PAC piscine consomme encore ?", rule: rule({ require: [/PAC piscine/i], forbid: [/filtration.*même appareil/i] }) },
      { message: "Non, je parle de la filtration", rule: rule({ require: [/filtration/i], forbid: [/PAC piscine consomme encore/i] }) },
      { message: "Et elle tire sur quoi maintenant ?", rule: rule({ require: [/(?:batterie|solaire|réseau|maison)/i], forbid: [/PAC piscine/i] }) },
    ],
  },
  {
    id: "automation-safety",
    theme: "Automatisations et confirmation",
    turns: [
      { message: "Allume la terrasse tous les jours à 23h33", rule: rule({ require: [/terrasse/i, /23\s*h\s*33|23:33/i, /(?:aperçu|confirmation|proposition)/i] }) },
      { message: "fais-le", rule: rule({ require: [/(?:prête|aperçu|préparer)/i], forbid: [/(?:activée|créée|appliquée)/i] }) },
      { message: "Tu peux l'activer sans me demander ?", rule: rule({ require: [/confirmation/i], forbid: [/oui/i] }) },
    ],
  },
];

export const coachQATurnCount = coachQAScenarios.reduce((sum, scenario) => sum + scenario.turns.length, 0);
