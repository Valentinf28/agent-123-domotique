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

type HistorySample = {
  capturedAt: string;
  homeWatts: number;
  solarWatts?: number;
  gridWatts?: number;
  batteryWatts?: number;
  filtrationWatts?: number;
  hotWaterWatts?: number;
  vehicleWatts?: number;
};

function measuredEnergyWh(
  history: HistorySample[],
  wattsForSample: (sample: HistorySample) => number,
) {
  const chronological = [...history].sort((left, right) =>
    Date.parse(left.capturedAt) - Date.parse(right.capturedAt));
  return chronological.reduce((total, sample, index) => {
    const next = chronological[index + 1];
    if (!next) return total;
    // A missing relay period must not be interpreted as continuous usage.
    const elapsedHours = Math.min(15 * 60_000, Math.max(0, Date.parse(next.capturedAt) - Date.parse(sample.capturedAt))) / 3_600_000;
    return total + Math.max(0, wattsForSample(sample)) * elapsedHours;
  }, 0);
}

function observedHistoryDays(history: HistorySample[]) {
  if (history.length < 2) return 0;
  const timestamps = history.map(({ capturedAt }) => Date.parse(capturedAt)).filter(Number.isFinite);
  return timestamps.length < 2 ? 0 : (Math.max(...timestamps) - Math.min(...timestamps)) / 86_400_000;
}

export type OffPeakPeriod = {
  id?: string;
  label?: string;
  start: string;
  end: string;
};

export type TariffPrices = {
  baseMilliEurosPerKwh: number | null;
  peakMilliEurosPerKwh: number | null;
  offPeakMilliEurosPerKwh: number | null;
  exportMilliEurosPerKwh: number | null;
};

const euroPrice = (milliEuros: number) => `${new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
}).format(milliEuros / 1000)} € / kWh`;

export function tariffGuidance(
  plan: "base" | "hp_hc",
  periods: OffPeakPeriod[],
  prices?: TariffPrices,
) {
  if (plan === "hp_hc" && periods.length) {
    const slots = periods.map((period) => `${period.start}–${period.end}`).join(", ");
    const configured = prices?.peakMilliEurosPerKwh != null && prices.offPeakMilliEurosPerKwh != null;
    const price = configured
      ? `Les prix renseignés sont ${euroPrice(prices.peakMilliEurosPerKwh!)} en heures pleines et ${euroPrice(prices.offPeakMilliEurosPerKwh!)} en heures creuses.`
      : "Sans les deux prix du kWh renseignés, le gain en euros ne peut pas être calculé honnêtement.";
    return `Le contrat comporte des heures creuses (${slots}). Utilisez-les comme solution de repli pour les appareils flexibles lorsque le solaire ne suffit pas. ${price}`;
  }
  if (plan === "hp_hc") {
    return "Le contrat est en heures pleines / heures creuses, mais aucune plage n’est configurée. Renseignez les horaires avant de proposer un décalage tarifaire. Sans prix du kWh renseigné, le gain en euros ne peut pas être calculé honnêtement.";
  }
  const price = prices?.baseMilliEurosPerKwh != null
    ? `Le prix renseigné est de ${euroPrice(prices.baseMilliEurosPerKwh)}.`
    : "Sans prix du kWh renseigné, le gain en euros ne peut pas être calculé honnêtement.";
  return `Le contrat est en option Base : décaler un usage ne réduit pas son prix à lui seul. Pour économiser, il faut prioriser le solaire disponible ou réduire la consommation. ${price}`;
}

export type CoachActionPlan = {
  status: "learning" | "ready";
  learningDays: number;
  targetDays: 14;
  daysRemaining: number;
  title: string;
  summary: string;
  actions: Array<{
    id: string;
    priority: number;
    goal: EnergyInsight["goal"];
    title: string;
    description: string;
    impact: string;
    nextStep: string;
  }>;
};

export function buildCoachActionPlan(input: {
  learningDays: number;
  historySamples: number;
  insights: EnergyInsight[];
  batteryReservePercent: number;
  tariffPlan: "base" | "hp_hc";
}): CoachActionPlan {
  const learningDays = Math.max(1, Math.min(14, Math.floor(input.learningDays)));
  const ready = learningDays >= 14 && input.historySamples >= 14 * 24 * 6;
  if (!ready) return {
    status: "learning",
    learningDays,
    targetDays: 14,
    daysRemaining: Math.max(0, 14 - learningDays),
    title: "Votre premier plan se prépare",
    summary: "Le Coach apprend les rythmes de la maison avant de recommander des changements durables.",
    actions: [],
  };

  const fallback: Record<EnergyInsight["goal"], EnergyInsight> = {
    money: {
      id: "plan-flexible-loads", icon: "€", tone: "tip", goal: "money", confidence: "estimated",
      title: "Décaler les usages flexibles",
      description: input.tariffPlan === "hp_hc"
        ? "Utiliser d’abord le solaire, puis les heures creuses configurées lorsque la production ne suffit pas."
        : "Utiliser d’abord le solaire : avec l’option Base, un simple changement d’heure ne réduit pas le prix du kWh.",
      impact: "Achats au réseau à réduire", action: "Quels appareils peut-on décaler ?",
    },
    battery: {
      id: "plan-battery-reserve", icon: "▣", tone: "attention", goal: "battery", confidence: "measured",
      title: "Protéger la réserve du soir",
      description: `Conserver le garde-fou batterie réglé à ${input.batteryReservePercent} % et reporter les usages non urgents quand il n’y a plus de solaire.`,
      impact: `Réserve minimale : ${input.batteryReservePercent} %`, action: "Quels usages préserver en priorité ?",
    },
    solar: {
      id: "plan-solar-priority", icon: "☀", tone: "positive", goal: "solar", confidence: "estimated",
      title: "Concentrer les cycles sur le solaire",
      description: "Placer PAC piscine, chauffe-eau et recharge sur les créneaux où la production couvre réellement leur puissance.",
      impact: "Autoconsommation à augmenter", action: "Quel est le meilleur créneau solaire ?",
    },
  };
  const actions = (["money", "battery", "solar"] as const).map((goal, index) => {
    const insight = input.insights.find((candidate) => candidate.goal === goal) ?? fallback[goal];
    return {
      id: insight.id,
      priority: index + 1,
      goal,
      title: insight.title,
      description: insight.description,
      impact: insight.impact,
      nextStep: insight.action,
    };
  });
  return {
    status: "ready",
    learningDays,
    targetDays: 14,
    daysRemaining: 0,
    title: "Votre plan d’action des 30 prochains jours",
    summary: "Trois actions prioritaires, calculées après deux semaines de mesures et réévaluées avec la maison.",
    actions,
  };
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
  const hourFormatter = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris", hour: "2-digit", hourCycle: "h23",
  });
  const observedDays = observedHistoryDays(history);
  const nightBase = average(history.filter((sample) => {
    const hour = Number(hourFormatter.formatToParts(new Date(sample.capturedAt))
      .find((part) => part.type === "hour")?.value);
    return hour >= 0 && hour < 5;
  }).map((sample) => sample.homeWatts));
  if (observedDays >= 7 && nightBase >= 250) {
    const monthlyShiftableKwh = Math.round(Math.max(0, nightBase - 150) * 8 * 30 / 1000);
    insights.push({
      id: "night-base", icon: "☾", tone: "attention", goal: "money", confidence: "estimated",
      title: "Consommation nocturne à examiner",
      description: `La maison consomme en moyenne ${Math.round(nightBase)} W pendant la nuit.`,
      impact: `Environ ${monthlyShiftableKwh} kWh / mois à examiner`,
      action: "Identifier les appareils en veille",
    });
  }

  if (observedDays >= 7) {
    const flexibleBatteryWh = measuredEnergyWh(history, (sample) => {
      if ((sample.solarWatts ?? 0) >= 100 || (sample.batteryWatts ?? 0) <= 300) return 0;
      return (sample.filtrationWatts ?? 0) + (sample.hotWaterWatts ?? 0) + (sample.vehicleWatts ?? 0);
    });
    if (flexibleBatteryWh >= 500) {
      const monthlyWh = flexibleBatteryWh * 30 / observedDays;
      insights.push({
        id: "historical-battery-flexible-loads", icon: "▣", tone: "attention",
        goal: "battery", confidence: "measured",
        title: "Des usages flexibles sollicitent la batterie",
        description: `${Math.round(flexibleBatteryWh / 100) / 10} kWh ont alimenté la filtration, le chauffe-eau ou la recharge sans solaire pendant la période observée.`,
        impact: `Environ ${Math.round(monthlyWh / 100) / 10} kWh / mois à déplacer`,
        action: "Quels usages décaler pour préserver la batterie ?",
      });
    }

    const exportedWh = measuredEnergyWh(history, (sample) => Math.max(0, -(sample.gridWatts ?? 0)));
    if (exportedWh >= 1_000) {
      const exportedByHour = new Map<number, number>();
      for (const sample of history) {
        const exported = Math.max(0, -(sample.gridWatts ?? 0));
        if (exported < 200) continue;
        const hour = Number(hourFormatter.formatToParts(new Date(sample.capturedAt))
          .find((part) => part.type === "hour")?.value);
        exportedByHour.set(hour, (exportedByHour.get(hour) ?? 0) + exported);
      }
      const bestHour = [...exportedByHour].sort((left, right) => right[1] - left[1])[0]?.[0];
      const period = Number.isFinite(bestHour) ? `, le plus souvent vers ${bestHour} h` : "";
      const monthlyWh = exportedWh * 30 / observedDays;
      insights.push({
        id: "historical-solar-export", icon: "☀", tone: "positive",
        goal: "solar", confidence: "measured",
        title: "Un surplus solaire revient régulièrement",
        description: `${Math.round(exportedWh / 100) / 10} kWh ont été injectés pendant la période observée${period}.`,
        impact: `Jusqu’à ${Math.round(monthlyWh / 100) / 10} kWh / mois à autoconsommer`,
        action: "Quels appareils peuvent absorber ce surplus ?",
      });
    }
  }

  const dominant = consumptionBreakdown.find((item) => item.id !== "other-home" && item.sharePercent >= 25);
  if (dominant) insights.push({
    id: `dominant-${dominant.id}`, icon: dominant.icon || "ϟ", tone: "tip",
    goal: "money", confidence: "measured",
    title: `${dominant.name} domine la consommation`,
    description: `${dominant.watts} W, soit environ ${dominant.sharePercent} % de la puissance mesurée de la maison actuellement.`,
    impact: "Premier poste à examiner maintenant",
    action: `Comment réduire la consommation de ${dominant.name} ?`,
  });

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
