export function observedPeriodLabel(observedDays: number) {
  const days = Math.max(1, Math.floor(observedDays));
  return days === 1
    ? 'Sur la journée disponible'
    : `Sur les ${days} derniers jours disponibles`;
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
