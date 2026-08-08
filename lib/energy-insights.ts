import type { ConsumptionBreakdownItem } from "./consumption-breakdown";
import type { EnergySnapshotValues } from "./energy-snapshot";

export type EnergyInsight = {
  id: string;
  icon: string;
  tone: "positive" | "attention" | "tip";
  goal: "money" | "battery" | "solar";
  confidence: "measured" | "estimated";
  title: string;
  description: string;
  impact: string;
  action: string;
};

type HistorySample = { capturedAt: string; homeWatts: number };

export type OffPeakPeriod = {
  id?: string;
  label?: string;
  start: string;
  end: string;
};

export function tariffGuidance(
  plan: "base" | "hp_hc",
  periods: OffPeakPeriod[],
) {
  if (plan === "hp_hc" && periods.length) {
    const slots = periods.map((period) => `${period.start}–${period.end}`).join(", ");
    return `Le contrat comporte des heures creuses (${slots}). Utilisez-les comme solution de repli pour les appareils flexibles lorsque le solaire ne suffit pas. Sans prix du kWh renseigné, le gain en euros ne peut pas être calculé honnêtement.`;
  }
  if (plan === "hp_hc") {
    return "Le contrat est en heures pleines / heures creuses, mais aucune plage n’est configurée. Renseignez les horaires avant de proposer un décalage tarifaire. Sans prix du kWh renseigné, le gain en euros ne peut pas être calculé honnêtement.";
  }
  return "Le contrat est en option Base : décaler un usage ne réduit pas son prix à lui seul. Pour économiser, il faut prioriser le solaire disponible ou réduire la consommation. Sans prix du kWh renseigné, le gain en euros ne peut pas être calculé honnêtement.";
}

const average = (values: number[]) => values.length
  ? values.reduce((sum, value) => sum + value, 0) / values.length
  : 0;

export function buildEnergyInsights(
  current: EnergySnapshotValues,
  history: HistorySample[],
  consumptionBreakdown: ConsumptionBreakdownItem[] = [],
  batteryReservePercent = 25,
): EnergyInsight[] {
  const insights: EnergyInsight[] = [];
  const dominant = consumptionBreakdown.find((item) => item.id !== "other-home" && item.sharePercent >= 25);
  if (dominant) insights.push({
    id: `dominant-${dominant.id}`, icon: dominant.icon || "ϟ", tone: "tip",
    goal: "money", confidence: "measured",
    title: `${dominant.name} domine la consommation`,
    description: `${dominant.watts} W, soit environ ${dominant.sharePercent} % de la puissance mesurée de la maison actuellement.`,
    impact: "Premier poste à examiner maintenant",
    action: `Comment réduire la consommation de ${dominant.name} ?`,
  });

  const hourFormatter = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris", hour: "2-digit", hourCycle: "h23",
  });
  const nightBase = average(history.filter((sample) => {
    const hour = Number(hourFormatter.formatToParts(new Date(sample.capturedAt))
      .find((part) => part.type === "hour")?.value);
    return hour >= 0 && hour < 5;
  }).map((sample) => sample.homeWatts));
  if (nightBase >= 250) {
    const monthlyShiftableKwh = Math.round(Math.max(0, nightBase - 150) * 8 * 30 / 1000);
    insights.push({
      id: "night-base", icon: "☾", tone: "attention", goal: "money", confidence: "estimated",
      title: "Consommation nocturne à examiner",
      description: `La maison consomme en moyenne ${Math.round(nightBase)} W pendant la nuit.`,
      impact: `Environ ${monthlyShiftableKwh} kWh / mois à examiner`,
      action: "Identifier les appareils en veille",
    });
  }

  const likelySurplus = Math.max(0, -current.gridWatts);
  if (likelySurplus >= 500 && current.batteryPercent >= 85) insights.push({
    id: "solar-surplus", icon: "☀", tone: "positive", goal: "solar", confidence: "measured",
    title: "Surplus solaire disponible",
    description: `${likelySurplus} W peuvent alimenter un équipement flexible maintenant.`,
    impact: "Autoconsommation à améliorer", action: "Planifier chauffe-eau ou véhicule",
  });
  if (current.hotWaterWatts > 500 && current.solarWatts < current.hotWaterWatts) insights.push({
    id: "hot-water", icon: "♨", tone: "tip", goal: "solar", confidence: "measured",
    title: "Chauffe-eau à décaler",
    description: "Le ballon fonctionne alors que la production solaire ne couvre pas sa puissance.",
    impact: "Décalage conseillé en journée", action: "Préparer une règle solaire",
  });
  if (current.vehicleWatts > 500 && current.solarWatts < current.vehicleWatts) insights.push({
    id: "vehicle-charge", icon: "◇", tone: "tip", goal: "solar", confidence: "measured",
    title: "Recharge à optimiser",
    description: "La voiture charge plus vite que la production solaire disponible.",
    impact: "Réduire les achats au réseau", action: "Adapter l’horaire de recharge",
  });

  if (current.batteryPercent > 0 && current.batteryPercent <= 20) insights.push({
    id: "battery-low", icon: "▣", tone: "attention", goal: "battery", confidence: "measured",
    title: "Réserve batterie faible", description: `La batterie est à ${current.batteryPercent} %.`,
    impact: "Garder une réserve pour le soir", action: "Vérifier la stratégie de batterie",
  });
  // Avant la nuit, attendre d'être presque à la réserve est trop tard : une
  // décharge significative sans solaire devient actionnable dès 65 %.
  const protectionThreshold = Math.max(65, batteryReservePercent + 20);
  if (current.batteryWatts > 300 && current.solarWatts < 100 && current.batteryPercent > 20 && current.batteryPercent <= protectionThreshold) insights.push({
    id: "battery-evening-discharge", icon: "▣", tone: "attention", goal: "battery", confidence: "measured",
    title: "Batterie sollicitée sans solaire",
    description: `La batterie fournit ${Math.round(current.batteryWatts)} W et il reste ${current.batteryPercent} %. Les usages flexibles peuvent attendre la prochaine production solaire.`,
    impact: `Réserve protégée à ${batteryReservePercent} %`,
    action: "Quels usages peut-on décaler à demain ?",
  });

  if (current.dailyProductionWh > 0 || current.dailyConsumptionWh > 0) {
    const coverage = current.dailyConsumptionWh > 0
      ? Math.min(100, Math.round(current.dailyProductionWh / current.dailyConsumptionWh * 100)) : 0;
    insights.push({
      id: "daily-balance", icon: "↗", tone: coverage >= 70 ? "positive" : "tip",
      goal: "solar", confidence: "measured", title: "Bilan de la journée",
      description: `${Math.round(current.dailyProductionWh / 100) / 10} kWh produits pour ${Math.round(current.dailyConsumptionWh / 100) / 10} kWh consommés.`,
      impact: `${coverage} % de couverture solaire théorique`, action: "Voir les pistes d’amélioration",
    });
  }
  if (!insights.length) insights.push({
    id: "learning", icon: "✦", tone: "positive", goal: "solar", confidence: "estimated",
    title: "Analyse en cours", description: "Le coach collecte progressivement les habitudes de la maison.",
    impact: "Premiers conseils après quelques heures", action: "Poser une question au coach",
  });

  const prioritized: EnergyInsight[] = [];
  for (const goal of ["money", "battery", "solar"] as const) {
    const insight = insights.find((candidate) => candidate.goal === goal);
    if (insight) prioritized.push(insight);
  }
  for (const insight of insights) {
    if (prioritized.length >= 4) break;
    if (!prioritized.some((candidate) => candidate.id === insight.id)) prioritized.push(insight);
  }
  return prioritized;
}
