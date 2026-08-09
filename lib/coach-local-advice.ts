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
  peakImportedWh: number;
  offPeakImportedWh: number;
  shiftableToSolarWh: number;
  shiftableSavingsEuros: number | null;
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
  const action = input.shiftableToSolarWh > 100
    ? input.shiftableSavingsEuros == null
      ? ` Priorité : déplacer jusqu’à ${kwh(input.shiftableToSolarWh * factor)} d’achats en journée vers le surplus chaque mois. Le tarif de rachat manque pour chiffrer honnêtement le gain net.`
      : ` Priorité : déplacer jusqu’à ${kwh(input.shiftableToSolarWh * factor)} d’achats en journée vers le surplus chaque mois, pour un gain net maximal estimé à ${euros(input.shiftableSavingsEuros * factor)} par mois.`
    : input.plan === 'hp_hc' && input.offPeakImportedWh > 0
      ? " Les achats en heures pleines sont déjà faibles ; conservez les heures creuses comme repli et priorisez le surplus solaire."
      : '';
  if (input.exportedWh > 0 && input.exportRevenueEuros == null) {
    return `${flows} ${purchase}, hors abonnement et taxes fixes. Le tarif de rachat n’est pas renseigné : l’injection n’est pas déduite de ce montant.${action} ${input.tariffGuidance}`;
  }
  if (input.netEnergyCostEuros != null) {
    const revenue = input.exportRevenueEuros && input.exportRevenueEuros > 0
      ? `, après environ ${euros(input.exportRevenueEuros * factor)} de rémunération de l’injection`
      : '';
    return `${flows} La part énergie nette projetée est d’environ ${euros(input.netEnergyCostEuros * factor)} par mois${revenue}, hors abonnement et taxes fixes.${action} C’est une projection fondée sur les flux réseau mesurés, pas une facture. ${input.tariffGuidance}`;
  }
  return `${flows} ${purchase}, hors abonnement et taxes fixes.${action} C’est une projection fondée sur les achats réseau mesurés, pas sur toute la consommation de la maison. ${input.tariffGuidance}`;
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

function parisDay(value: string | Date) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(value));
}

function relativeDayLabel(now: Date, target: Date) {
  const nowDay = parisDay(now);
  const targetDay = parisDay(target);
  if (targetDay === nowDay) return "aujourd’hui";
  const difference = Math.round((Date.parse(`${targetDay}T12:00:00Z`) - Date.parse(`${nowDay}T12:00:00Z`)) / 86_400_000);
  if (difference === 1) return 'demain';
  return `le ${new Intl.DateTimeFormat('fr-FR', { timeZone: 'Europe/Paris', day: 'numeric', month: 'long' }).format(target)}`;
}

export function vehicleChargingGuidance(input: {
  now: Date;
  vehicleWatts: number;
  currentExportWatts: number;
  forecastSlots: Array<{ startsAt: string; estimatedWh: number }>;
  forecastConfidence: 'high' | 'medium' | 'low';
  reservePercent: number;
  offPeakPeriods: Array<{ start: string; end: string }>;
}) {
  if (input.vehicleWatts > 100) {
    return `La voiture charge actuellement à ${new Intl.NumberFormat('fr-FR').format(Math.round(input.vehicleWatts))} W. Conservez une intensité ajustée au surplus et la réserve batterie à ${input.reservePercent} %.`;
  }
  if (input.currentExportWatts > 300) {
    return `La voiture ne charge pas et ${new Intl.NumberFormat('fr-FR').format(Math.round(input.currentExportWatts))} W sont actuellement injectés. Si elle est branchée, démarrez progressivement sur ce surplus sans faire passer la batterie sous ${input.reservePercent} %.`;
  }
  const future = input.forecastSlots.filter((slot) => Date.parse(slot.startsAt) > input.now.getTime());
  const peak = [...future].sort((left, right) => right.estimatedWh - left.estimatedWh)[0];
  if (peak && peak.estimatedWh >= 300) {
    const target = new Date(peak.startsAt);
    const time = new Intl.DateTimeFormat('fr-FR', {
      timeZone: 'Europe/Paris', hour: '2-digit', minute: '2-digit',
    }).format(target);
    const confidence = input.forecastConfidence === 'low'
      ? "La confiance est faible : attendez que le surplus soit réellement mesuré avant de lancer ou d’augmenter la charge."
      : "La borne peut augmenter progressivement la charge lorsque le surplus est réellement mesuré.";
    const fallback = input.offPeakPeriods.length
      ? ` Si la voiture doit être prête avant, utilisez en repli les heures creuses ${input.offPeakPeriods.map((period) => `${period.start}–${period.end}`).join(', ')}.`
      : '';
    return `Le meilleur point de la prévision est ${relativeDayLabel(input.now, target)} vers ${time}. ${confidence} La réserve batterie reste fixée à ${input.reservePercent} %.${fallback}`;
  }
  const fallback = input.offPeakPeriods.length
    ? `Utilisez en repli les heures creuses ${input.offPeakPeriods.map((period) => `${period.start}–${period.end}`).join(', ')} si la voiture doit être prête.`
    : "Choisissez une recharge manuelle selon l’heure de départ souhaitée.";
  return `Aucun créneau solaire suffisamment fiable n’est disponible pour le moment. ${fallback} Ne sollicitez pas la batterie sous sa réserve de ${input.reservePercent} %.`;
}

export function batterySavingsGuidance(pricesConfigured: boolean) {
  const price = pricesConfigured
    ? 'Le tarif est configuré, mais il manque encore le bilan dédié des cycles de batterie pour isoler ce gain.'
    : 'Le prix du kWh n’est pas renseigné et le gain ne peut pas être converti honnêtement en euros.';
  return `Pour calculer l’économie apportée par la batterie, il faut mesurer l’énergie qu’elle restitue à la place d’un achat réseau, puis déduire ses pertes. ${price} Le Coach peut néanmoins protéger la réserve et éviter les décharges pour des usages reportables.`;
}

export function filtrationBatteryProtectionGuidance(input: {
  reservePercent: number;
  filtrationWatts: number;
  configuredForEnergyControl: boolean;
}) {
  const anticipationPercent = Math.min(100, input.reservePercent + 5);
  const measuredPower = input.filtrationWatts > 100
    ? ` La filtration consomme actuellement environ ${new Intl.NumberFormat('fr-FR').format(Math.round(input.filtrationWatts))} W.`
    : '';
  const setup = input.configuredForEnergyControl
    ? "Le pilotage énergétique peut appliquer ce comportement en contrôlant le surplus réel et la réserve."
    : "Pour l’automatiser correctement, la filtration doit d’abord être déclarée comme usage flexible pilotable ; je ne fabriquerai pas une simple heure fixe qui ignorerait la météo et la batterie.";
  return [
    `Vous avez raison sur le principe : si le cycle pouvait être reporté, la filtration aurait dû être suspendue avant que la batterie atteigne sa réserve de ${input.reservePercent} %.${measuredPower}`,
    `Je recommande ce garde-fou : à ${anticipationPercent} %, mettre la filtration en pause si le solaire ne couvre pas sa puissance, puis la relancer uniquement quand le surplus réel suffit.`,
    "La durée quotidienne nécessaire doit être terminée plus tard et les protections antigel ou sanitaires restent toujours prioritaires.",
    setup,
  ].join(' ');
}

export function unavailableEquipmentGuidance(
  intent: 'vehicle' | 'hot-water',
  capabilities: { vehicle: boolean; hotWater: boolean },
) {
  if (intent === 'vehicle' && !capabilities.vehicle) {
    return 'Aucune borne ni voiture compatible n’est actuellement remontée par la box 1.2.3. Home. Le Coach ne peut pas confirmer une recharge ni proposer une règle avant la configuration de l’équipement.';
  }
  if (intent === 'hot-water' && !capabilities.hotWater) {
    return 'Aucun chauffe-eau pilotable n’est actuellement remonté par la box 1.2.3. Home. Le Coach ne peut donc ni confirmer son état ni proposer une automatisation. Vérifiez d’abord sa présence dans les équipements.';
  }
  return null;
}
