export function observedPeriodLabel(observedDays: number) {
  const days = Math.max(1, Math.floor(observedDays));
  return days === 1
    ? 'Sur la journée disponible'
    : `Sur les ${days} derniers jours disponibles`;
}

function euros(value: number) {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}

function kwh(valueWh: number) {
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(Math.max(0, valueWh) / 1000)} kWh`;
}

export function financialCoachGuidance(input: {
  observedDays: number;
  importedWh: number;
  exportedWh: number;
  importCostEuros: number | null;
  exportRevenueEuros: number | null;
  netEnergyCostEuros: number | null;
  plan: 'base' | 'hp_hc';
  tariffGuidance: string;
}) {
  const days = Math.max(1, input.observedDays);
  const factor = 30 / days;
  const period = observedPeriodLabel(days);
  const flows = `${period}, la maison a acheté ${kwh(input.importedWh)} au réseau et injecté ${kwh(input.exportedWh)}.`;
  if (input.importCostEuros == null) {
    return `${flows} Le prix d’achat correspondant n’est pas entièrement renseigné : le Coach ne fabrique donc aucun montant. ${input.tariffGuidance}`;
  }
  const purchase = `À rythme identique, les achats d’énergie représenteraient environ ${euros(input.importCostEuros * factor)} par mois`;
  if (input.exportedWh > 0 && input.exportRevenueEuros == null) {
    return `${flows} ${purchase}, hors abonnement et taxes fixes. Le tarif de rachat n’est pas renseigné : l’injection n’est pas déduite de ce montant. ${input.tariffGuidance}`;
  }
  if (input.netEnergyCostEuros != null) {
    const revenue = input.exportRevenueEuros && input.exportRevenueEuros > 0
      ? `, après environ ${euros(input.exportRevenueEuros * factor)} de rémunération de l’injection`
      : '';
    return `${flows} La part énergie nette projetée est d’environ ${euros(input.netEnergyCostEuros * factor)} par mois${revenue}, hors abonnement et taxes fixes. C’est une projection fondée sur les flux réseau mesurés, pas une facture. ${input.tariffGuidance}`;
  }
  return `${flows} ${purchase}, hors abonnement et taxes fixes. C’est une projection fondée sur les achats réseau mesurés, pas sur toute la consommation de la maison. ${input.tariffGuidance}`;
}

export function solarCoachGuidance(input: {
  forecastAvailable: boolean;
  exportWatts: number;
  prudentRemainingKwh: string;
}) {
  const exportWatts = Math.max(0, Math.round(input.exportWatts));
  const current = exportWatts > 100
    ? `La maison exporte actuellement environ ${new Intl.NumberFormat('fr-FR').format(exportWatts)} W.`
    : "Il n’y a pas de surplus significatif mesuré maintenant.";
  if (!input.forecastAvailable) {
    return `${current} Aucune prévision solaire exploitable n’est disponible ; le Coach ne propose donc pas de créneau futur et conserve les garde-fous batterie.`;
  }
  const next = exportWatts > 100
    ? 'Un appareil flexible peut être déplacé sur ce créneau si ses garde-fous le permettent.'
    : 'Mieux vaut conserver les garde-fous batterie avant de déplacer un appareil.';
  return `${current} La prévision prudente estime encore ${input.prudentRemainingKwh} à produire aujourd’hui ; ${next}`;
}

export function solarAutoconsumptionGuidance(input: {
  observedDays: number;
  exportedWh: number;
  peakHour: number | null;
  flexibleLoads: Array<{ label: string; category: string }>;
  currentExportWatts: number;
}) {
  const days = Math.max(1, input.observedDays);
  const dailyKwh = input.exportedWh / 1000 / days;
  const peak = input.peakHour == null ? '' : `, le plus souvent autour de ${input.peakHour} h`;
  const measured = `Sur ${days} jours, ${kwh(input.exportedWh)} ont été injectés${peak}, soit environ ${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(dailyKwh)} kWh par jour.`;
  const distinct = [...new Map(input.flexibleLoads.map((load) => [load.label, load])).values()];
  const priority = distinct.length
    ? `Les usages pilotables configurés à tester en priorité sont : ${distinct.map((load) => load.label).join(', ')}.`
    : "Aucun usage flexible pilotable n’est encore configuré : le Coach ne peut pas proposer honnêtement de règle d’absorption du surplus.";
  const now = input.currentExportWatts > 100
    ? `Il y a actuellement ${new Intl.NumberFormat('fr-FR').format(Math.round(input.currentExportWatts))} W de surplus.`
    : "Il n’y a pas de surplus mesuré maintenant : aucun démarrage immédiat n’est conseillé.";
  return `${measured} ${priority} ${now} Pour préserver la batterie, un appareil ne doit démarrer que lorsque sa puissance est couverte ; la PAC piscine doit aussi être arrêtée au coucher du soleil si elle n’a plus besoin de chauffer.`;
}

export function batterySavingsGuidance(pricesConfigured: boolean) {
  const price = pricesConfigured
    ? 'Le tarif est configuré, mais il manque encore le bilan dédié des cycles de batterie pour isoler ce gain.'
    : 'Le prix du kWh n’est pas renseigné et le gain ne peut pas être converti honnêtement en euros.';
  return `Pour calculer l’économie apportée par la batterie, il faut mesurer l’énergie qu’elle restitue à la place d’un achat réseau, puis déduire ses pertes. ${price} Le Coach peut néanmoins protéger la réserve et éviter les décharges pour des usages reportables.`;
}

export function unavailableEquipmentGuidance(
  intent: 'vehicle' | 'hot-water',
  capabilities: { vehicle: boolean; hotWater: boolean },
) {
  if (intent === 'vehicle' && !capabilities.vehicle) {
    return 'Aucune borne ni voiture compatible n’est actuellement remontée par la box 1.2.3 Home. Le Coach ne peut pas confirmer une recharge ni proposer une règle avant la configuration de l’équipement.';
  }
  if (intent === 'hot-water' && !capabilities.hotWater) {
    return 'Aucun chauffe-eau pilotable n’est actuellement remonté par la box 1.2.3 Home. Le Coach ne peut donc ni confirmer son état ni proposer une automatisation. Vérifiez d’abord sa présence dans les équipements.';
  }
  return null;
}
