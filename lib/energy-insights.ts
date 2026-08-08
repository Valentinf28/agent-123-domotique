export type EnergyInsightSnapshot = {
  solarWatts: number;
  homeWatts: number;
  gridWatts: number;
  batteryPercent: number;
  batteryWatts: number;
  filtrationWatts: number;
  hotWaterWatts: number;
  vehicleWatts: number;
  dailyProductionWh: number;
  dailyConsumptionWh: number;
};

export type EnergyHistorySample = EnergyInsightSnapshot & { capturedAt: string };

export type CalculatedEnergyInsight = {
  id: string;
  icon: string;
  tone: "positive" | "attention" | "tip";
  title: string;
  description: string;
  impact: string;
  action: string;
};

function average(values: number[]) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function localHour(isoDate: string, timeZone: string) {
  const hour = new Intl.DateTimeFormat("fr-FR", {
    timeZone,
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(isoDate)).find((part) => part.type === "hour")?.value;
  return Number(hour);
}

export function energyInsights(
  current: EnergyInsightSnapshot,
  history: EnergyHistorySample[],
  timeZone = "Europe/Paris",
): CalculatedEnergyInsight[] {
  const insights: CalculatedEnergyInsight[] = [];
  const nightSamples = history.filter((sample) => {
    const hour = localHour(sample.capturedAt, timeZone);
    return hour >= 0 && hour < 5;
  });
  const nightBase = average(nightSamples.map((sample) => sample.homeWatts));
  if (nightSamples.length >= 8 && nightBase >= 250) {
    const avoidableWatts = Math.max(0, nightBase - 150);
    const avoidableMonthlyKwh = avoidableWatts * 5 * 30 / 1000;
    insights.push({
      id: "night-base", icon: "☾", tone: "attention",
      title: "Consommation nocturne à examiner",
      description: `La maison consomme en moyenne ${Math.round(nightBase)} W pendant la nuit.`,
      impact: `Jusqu’à ${Math.round(avoidableMonthlyKwh)} kWh / mois à examiner`,
      action: "Identifier les appareils en veille",
    });
  }

  // Le flux réseau est la seule preuve d'un surplus réellement injecté. Une différence
  // production/maison ignorerait la charge de la batterie et créerait de faux conseils.
  const likelySurplus = Math.max(0, -current.gridWatts);
  if (likelySurplus >= 500 && current.batteryPercent >= 85) {
    insights.push({
      id: "solar-surplus", icon: "☀", tone: "positive",
      title: "Surplus solaire disponible",
      description: `${likelySurplus} W sont réellement injectés et peuvent alimenter un équipement flexible maintenant.`,
      impact: "Autoconsommation à améliorer",
      action: "Planifier chauffe-eau ou véhicule",
    });
  }
  if (current.hotWaterWatts > 500 && current.solarWatts < current.hotWaterWatts) {
    insights.push({
      id: "hot-water", icon: "♨", tone: "tip", title: "Chauffe-eau à décaler",
      description: "Le ballon fonctionne alors que la production solaire ne couvre pas sa puissance.",
      impact: "Décalage conseillé en journée", action: "Préparer une règle solaire",
    });
  }
  if (current.vehicleWatts > 500 && current.solarWatts < current.vehicleWatts) {
    insights.push({
      id: "vehicle-charge", icon: "◇", tone: "tip", title: "Recharge à optimiser",
      description: "La voiture charge plus vite que la production solaire disponible.",
      impact: "Réduire les achats au réseau", action: "Adapter l’horaire de recharge",
    });
  }
  if (current.batteryPercent > 0 && current.batteryPercent <= 20) {
    insights.push({
      id: "battery-low", icon: "▣", tone: "attention", title: "Réserve batterie faible",
      description: `La batterie est à ${current.batteryPercent} %.`,
      impact: "Garder une réserve pour le soir", action: "Vérifier la stratégie de batterie",
    });
  }
  if (current.dailyProductionWh > 0 || current.dailyConsumptionWh > 0) {
    const productionConsumptionRatio = current.dailyConsumptionWh > 0
      ? Math.min(100, Math.round(current.dailyProductionWh / current.dailyConsumptionWh * 100)) : 0;
    insights.push({
      id: "daily-balance", icon: "↗", tone: productionConsumptionRatio >= 70 ? "positive" : "tip",
      title: "Bilan de la journée",
      description: `${Math.round(current.dailyProductionWh / 100) / 10} kWh produits pour ${Math.round(current.dailyConsumptionWh / 100) / 10} kWh consommés.`,
      impact: `Production équivalente à ${productionConsumptionRatio} % de la consommation`,
      action: "Voir les pistes d’amélioration",
    });
  }
  if (!insights.length) {
    insights.push({
      id: "learning", icon: "✦", tone: "positive", title: "Analyse en cours",
      description: "Le coach collecte progressivement les habitudes de la maison.",
      impact: "Premiers conseils après quelques heures", action: "Poser une question au coach",
    });
  }
  return insights.slice(0, 4);
}
