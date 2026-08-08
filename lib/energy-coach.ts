import { and, desc, eq, gt, gte, lt, sql } from "drizzle-orm";
import { getDb } from "../db";
import { assistantUsage, energySnapshots } from "../db/schema";
import { selectAgentForDossier } from "./agent-home";
import {
  buildAdaptiveSolarForecast,
  buildPredictiveEnergyPlan,
  type SolarForecastSlot,
} from "./predictive-energy";
import {
  energySnapshotFromInventory,
  type EnergyInventoryItem,
  type EnergySnapshotValues,
} from "./energy-snapshot";
import {
  ASSISTANT_MONTHLY_LIMIT,
  assistantQuotaAllows,
  assistantQuotaBucket,
  type AssistantQuotaKind,
} from "./assistant-quota";
import {
  consumptionBreakdownFromInventory,
  type ConsumptionBreakdownItem,
} from "./consumption-breakdown";
import { HOUSE_BINDINGS } from "./house-bindings.generated";
import { resolveEntityCandidate } from "./entity-resolution.generated.js";
import { buildEnergyInsights as buildPrioritizedEnergyInsights } from "./energy-insights";
import { buildCoachActionPlan } from "./energy-insights";
import type { OffPeakPeriod } from "./energy-insights";
import { equipmentCapabilitiesFromInventory } from "./equipment-capabilities";
import { buildBatteryNightOutlook } from "./battery-night-outlook";
export {
  ASSISTANT_MONTHLY_LIMIT,
  assistantQuotaAllows,
  assistantQuotaBucket,
} from "./assistant-quota";
export type { AssistantQuotaKind } from "./assistant-quota";
export { energySnapshotFromInventory } from "./energy-snapshot";
export type { EnergyInventoryItem, EnergySnapshotValues } from "./energy-snapshot";

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

type FlexibleLoadConfiguration = {
  id: string;
  name: string;
  category: string;
  icon: string;
  powerWatts: number;
  minimumRunMinutes: number;
  priority: number;
  enabled: boolean;
  powerEntityId?: string;
  showInConsumption?: boolean;
};

const bindings = {
  forecastTodayKwh: [
    "sensor.maison_energy_production_today",
    "sensor.energy_production_today",
  ],
  forecastRemainingKwh: [
    "sensor.maison_energy_production_today_remaining",
    "sensor.energy_production_today_remaining",
  ],
  forecastSolarWatts: [
    "sensor.maison_power_production_now",
    "sensor.power_production_now",
  ],
  cloudCoverPercent: [
    "sensor.escorpain_cloud_cover",
    "sensor.cloud_cover",
  ],
  poolTemperature: [...HOUSE_BINDINGS.poolWaterTemperature, "input_number.demo_pool_temperature"],
  poolHeatPump: [...HOUSE_BINDINGS.poolHeatPump, "input_boolean.demo_pool_heat_pump"],
} as const;

function parseInventory(value: string): EnergyInventoryItem[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item): item is EnergyInventoryItem =>
      Boolean(item && typeof item.entityId === "string" && typeof item.state === "string")
    ) : [];
  } catch {
    return [];
  }
}

function numberFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = inventoryItemFrom(inventory, ids);
  const value = Number(item?.state);
  return Number.isFinite(value) ? value : 0;
}

function nullableNumberFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = inventoryItemFrom(inventory, ids);
  const value = Number(item?.state);
  return Number.isFinite(value) ? value : null;
}

function activeFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = inventoryItemFrom(inventory, ids);
  return Boolean(item && ["on", "heat", "heating"].includes(item.state.toLowerCase()));
}

function inventoryItemFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const candidate = resolveEntityCandidate(inventory.map((item) => ({
    item,
    entityId: item.entityId,
    name: item.name,
    deviceClass: item.deviceClass ?? "",
    state: item.state,
  })), ids);
  return candidate?.item ?? null;
}

function attributeNumberFrom(
  inventory: EnergyInventoryItem[],
  ids: readonly string[],
  key: string,
) {
  const parsed = Number(inventoryItemFrom(inventory, ids)?.attributes?.[key]);
  return Number.isFinite(parsed) ? parsed : null;
}

function flexibleLoadsFrom(value: string): FlexibleLoadConfiguration[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is FlexibleLoadConfiguration =>
        Boolean(
          item &&
          typeof item.id === "string" &&
          typeof item.name === "string" &&
          typeof item.powerWatts === "number" &&
          typeof item.minimumRunMinutes === "number",
        )
      )
      : [];
  } catch {
    return [];
  }
}

function offPeakPeriodsFrom(value: string): OffPeakPeriod[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((period): period is OffPeakPeriod =>
      Boolean(period && typeof period.start === "string" && typeof period.end === "string")
    ) : [];
  } catch {
    return [];
  }
}

function loadState(
  load: FlexibleLoadConfiguration,
  inventory: EnergyInventoryItem[],
  current: EnergySnapshotValues,
) {
  if (load.category === "pool") {
    const temperature = nullableNumberFrom(inventory, bindings.poolTemperature);
    const setpoint = attributeNumberFrom(inventory, bindings.poolHeatPump, "temperature");
    const needed = temperature === null || setpoint === null || temperature < setpoint - 0.2;
    return {
      alreadyRunning: activeFrom(inventory, bindings.poolHeatPump),
      needed,
      needReason: needed
        ? "La température cible n’est pas encore atteinte."
        : `La piscine est déjà proche de sa consigne (${temperature?.toFixed(1)} °C).`,
    };
  }
  if (load.category === "hot_water") {
    return {
      alreadyRunning: current.hotWaterWatts > 100,
      needed: true,
      needReason: "Le cycle quotidien peut être déplacé vers le meilleur créneau solaire.",
    };
  }
  if (load.category === "vehicle") {
    return {
      alreadyRunning: current.vehicleWatts > 100,
      needed: true,
      needReason: "La recharge demandée peut être répartie sur les heures les plus favorables.",
    };
  }
  if (load.category === "filtration") {
    return {
      alreadyRunning: current.filtrationWatts > 100,
      needed: true,
      needReason: "La durée quotidienne de filtration peut être déplacée sans réduire le service.",
    };
  }
  return {
    alreadyRunning: false,
    needed: true,
    needReason: "Ce besoin flexible peut être déplacé vers un créneau plus favorable.",
  };
}

export function solarForecastFromInventory(
  inventory: EnergyInventoryItem[],
): SolarForecastSlot[] {
  const prefix = "Prévision solaire ";
  return inventory
    .filter((item) =>
      item.entityId.startsWith("sensor.1_2_3_home_solar_forecast_") &&
      item.name.startsWith(prefix)
    )
    .map((item) => ({
      startsAt: item.name.slice(prefix.length),
      estimatedWh: Math.max(0, Math.round(Number(item.state) || 0)),
    }))
    .filter((slot) => Number.isFinite(Date.parse(slot.startsAt)))
    .sort((left, right) => Date.parse(left.startsAt) - Date.parse(right.startsAt));
}

export function fiveMinuteBucket(date: Date) {
  const minutes = Math.floor(date.getUTCMinutes() / 5) * 5;
  const bucket = new Date(date);
  bucket.setUTCMinutes(minutes, 0, 0);
  return bucket.toISOString();
}

function average(values: number[]) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function buildEnergyInsights(
  current: EnergySnapshotValues,
  history: Array<Pick<typeof energySnapshots.$inferSelect, "capturedAt" | "homeWatts">>,
  consumptionBreakdown: ConsumptionBreakdownItem[] = [],
  batteryReservePercent = 25,
): EnergyInsight[] {
  const insights: EnergyInsight[] = [];
  const dominant = consumptionBreakdown.find((item) => item.id !== "other-home" && item.sharePercent >= 25);
  if (dominant) {
    insights.push({
      id: `dominant-${dominant.id}`,
      icon: dominant.icon || "ϟ",
      tone: "tip",
      goal: "money",
      confidence: "measured",
      title: `${dominant.name} domine la consommation`,
      description: `${dominant.watts} W, soit environ ${dominant.sharePercent} % de la puissance mesurée de la maison actuellement.`,
      impact: "Premier poste à examiner maintenant",
      action: `Comment réduire la consommation de ${dominant.name} ?`,
    });
  }
  const nightHour = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    hourCycle: "h23",
  });
  const nightSamples = history.filter((sample) => {
    const hour = Number(nightHour.formatToParts(new Date(sample.capturedAt))
      .find((part) => part.type === "hour")?.value);
    return hour >= 0 && hour < 5;
  });
  const nightBase = average(nightSamples.map((sample) => sample.homeWatts));
  if (nightBase >= 250) {
    const avoidableWatts = Math.max(0, nightBase - 150);
    const monthlyShiftableKwh = Math.round(avoidableWatts * 8 * 30 / 1000);
    insights.push({
      id: "night-base",
      icon: "☾",
      tone: "attention",
      goal: "money",
      confidence: "estimated",
      title: "Consommation nocturne à examiner",
      description: `La maison consomme en moyenne ${Math.round(nightBase)} W pendant la nuit.`,
      impact: `Environ ${monthlyShiftableKwh} kWh / mois à examiner`,
      action: "Identifier les appareils en veille",
    });
  }

  // Le réseau négatif correspond à un export. Utiliser la mesure réelle évite
  // d'annoncer un surplus lorsque la batterie absorbe l'écart ou que l'onduleur
  // bride volontairement la production en zéro injection.
  const likelySurplus = Math.max(0, -current.gridWatts);
  if (likelySurplus >= 500 && current.batteryPercent >= 85) {
    insights.push({
      id: "solar-surplus",
      icon: "☀",
      tone: "positive",
      goal: "solar",
      confidence: "measured",
      title: "Surplus solaire disponible",
      description: `${likelySurplus} W peuvent alimenter un équipement flexible maintenant.`,
      impact: "Autoconsommation à améliorer",
      action: "Planifier chauffe-eau ou véhicule",
    });
  }

  if (current.hotWaterWatts > 500 && current.solarWatts < current.hotWaterWatts) {
    insights.push({
      id: "hot-water",
      icon: "♨",
      tone: "tip",
      goal: "solar",
      confidence: "measured",
      title: "Chauffe-eau à décaler",
      description: "Le ballon fonctionne alors que la production solaire ne couvre pas sa puissance.",
      impact: "Décalage conseillé en journée",
      action: "Préparer une règle solaire",
    });
  }

  if (current.vehicleWatts > 500 && current.solarWatts < current.vehicleWatts) {
    insights.push({
      id: "vehicle-charge",
      icon: "◇",
      tone: "tip",
      goal: "solar",
      confidence: "measured",
      title: "Recharge à optimiser",
      description: "La voiture charge plus vite que la production solaire disponible.",
      impact: "Réduire les achats au réseau",
      action: "Adapter l’horaire de recharge",
    });
  }

  if (current.batteryPercent > 0 && current.batteryPercent <= 20) {
    insights.push({
      id: "battery-low",
      icon: "▣",
      tone: "attention",
      goal: "battery",
      confidence: "measured",
      title: "Réserve batterie faible",
      description: `La batterie est à ${current.batteryPercent} %.`,
      impact: "Garder une réserve pour le soir",
      action: "Vérifier la stratégie de batterie",
    });
  }

  const batteryProtectionThreshold = Math.max(35, batteryReservePercent + 15);
  if (
    current.batteryWatts > 300 &&
    current.solarWatts < 100 &&
    current.batteryPercent > 20 &&
    current.batteryPercent <= batteryProtectionThreshold
  ) {
    insights.push({
      id: "battery-evening-discharge",
      icon: "▣",
      tone: "attention",
      goal: "battery",
      confidence: "measured",
      title: "Batterie sollicitée sans solaire",
      description: `La batterie fournit ${Math.round(current.batteryWatts)} W et il reste ${current.batteryPercent} %. Les usages flexibles peuvent attendre la prochaine production solaire.`,
      impact: `Réserve protégée à ${batteryReservePercent} %`,
      action: "Quels usages peut-on décaler à demain ?",
    });
  }

  if (current.dailyProductionWh > 0 || current.dailyConsumptionWh > 0) {
    const selfCoverage = current.dailyConsumptionWh > 0
      ? Math.min(100, Math.round(current.dailyProductionWh / current.dailyConsumptionWh * 100))
      : 0;
    insights.push({
      id: "daily-balance",
      icon: "↗",
      tone: selfCoverage >= 70 ? "positive" : "tip",
      goal: "solar",
      confidence: "measured",
      title: "Bilan de la journée",
      description: `${Math.round(current.dailyProductionWh / 100) / 10} kWh produits pour ${Math.round(current.dailyConsumptionWh / 100) / 10} kWh consommés.`,
      impact: `${selfCoverage} % de couverture solaire théorique`,
      action: "Voir les pistes d’amélioration",
    });
  }

  if (!insights.length) {
    insights.push({
      id: "learning",
      icon: "✦",
      tone: "positive",
      goal: "solar",
      confidence: "estimated",
      title: "Analyse en cours",
      description: "Le coach collecte progressivement les habitudes de la maison.",
      impact: "Premiers conseils après quelques heures",
      action: "Poser une question au coach",
    });
  }
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

export async function getEnergyCoachContext(dossierPublicId?: string | null) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const current = energySnapshotFromInventory(inventory);
  const now = new Date();
  const since = new Date(now.getTime() - 15 * 24 * 60 * 60 * 1000).toISOString();
  const history = await getDb().select().from(energySnapshots)
    .where(and(
      eq(energySnapshots.dossierId, selected.dossier.id),
      gte(energySnapshots.capturedAt, since),
    ))
    .orderBy(desc(energySnapshots.capturedAt))
    // Quinze jours permettent de confirmer deux semaines pleines malgré les
    // décalages entre le premier relevé et l'heure de consultation.
    .limit(15 * 24 * 12 + 12);
  const forecast = solarForecastFromInventory(inventory);
  const adaptiveForecast = buildAdaptiveSolarForecast({
    now: new Date(),
    forecast,
    actualSolarWatts: current.solarWatts,
    forecastSolarWatts: numberFrom(inventory, bindings.forecastSolarWatts),
    actualTodayWh: current.dailyProductionWh,
    forecastTodayWh: numberFrom(inventory, bindings.forecastTodayKwh) * 1000,
    forecastRemainingWh: numberFrom(inventory, bindings.forecastRemainingKwh) * 1000,
    cloudCoverPercent: nullableNumberFrom(inventory, bindings.cloudCoverPercent),
  });
  const baseSamples = history.map((sample) =>
    Math.max(
      0,
      sample.homeWatts -
      sample.filtrationWatts -
      sample.hotWaterWatts,
    )
  ).filter((value) => value > 0);
  const currentBaseLoad = Math.max(
    0,
    current.homeWatts -
    current.filtrationWatts -
    current.hotWaterWatts,
  );
  const baseLoadWatts = Math.round(Math.max(
    150,
    baseSamples.length ? average(baseSamples.slice(0, 192)) : currentBaseLoad,
  ));
  const configuredLoads = flexibleLoadsFrom(selected.dossier.flexibleLoadsJson)
    .filter((load) => load.enabled)
    .sort((left, right) => left.priority - right.priority);
  const consumptionBreakdown = consumptionBreakdownFromInventory(
    inventory,
    configuredLoads,
    current.homeWatts,
  );
  const equipmentCapabilities = equipmentCapabilitiesFromInventory(inventory);
  const loadsForPlanning = configuredLoads.length ? configuredLoads : [{
    id: "configuration",
    name: "Appareils flexibles",
    category: "other",
    icon: "ϟ",
    powerWatts: 0,
    minimumRunMinutes: 60,
    priority: 1,
    enabled: true,
  }];
  const predictivePlans = loadsForPlanning.map((load) => {
    const state = loadState(load, inventory, current);
    return buildPredictiveEnergyPlan({
      now: new Date(),
      batteryPercent: current.batteryPercent,
      baseLoadWatts,
      forecast: adaptiveForecast.prudentSlots,
      forecastConfidence: adaptiveForecast.confidence,
      load: {
        id: load.id,
        label: load.name,
        category: load.category,
        powerWatts: load.powerWatts,
        minimumRunMinutes: load.minimumRunMinutes,
        alreadyRunning: state.alreadyRunning,
        needed: state.needed,
        needReason: state.needReason,
      },
      settings: {
        batteryCapacityWh: selected.dossier.batteryCapacityWh,
        batteryReservePercent: selected.dossier.batteryReservePercent,
      },
    });
  });
  const predictivePlan = predictivePlans[0];
  const daily = new Map<string, { productionWh: number; consumptionWh: number }>();
  const parisDay = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  for (const sample of history) {
    const day = parisDay.format(new Date(sample.capturedAt));
    const previous = daily.get(day) ?? { productionWh: 0, consumptionWh: 0 };
    daily.set(day, {
      productionWh: Math.max(previous.productionWh, sample.dailyProductionWh),
      consumptionWh: Math.max(previous.consumptionWh, sample.dailyConsumptionWh),
    });
  }
  const week = Array.from(daily.values()).reduce((total, day) => ({
    productionWh: total.productionWh + day.productionWh,
    consumptionWh: total.consumptionWh + day.consumptionWh,
    observedDays: total.observedDays,
  }), { productionWh: 0, consumptionWh: 0, observedDays: Math.max(1, daily.size) });
  const firstCapturedAt = history.length
    ? Math.min(...history.map((sample) => Date.parse(sample.capturedAt)))
    : now.getTime();
  const learningDays = Math.max(1, Math.floor((now.getTime() - firstCapturedAt) / (24 * 60 * 60 * 1000)));
  const insights = buildPrioritizedEnergyInsights(
    current,
    history,
    consumptionBreakdown,
    selected.dossier.batteryReservePercent,
  );
  const actionPlan = buildCoachActionPlan({
    learningDays,
    historySamples: history.length,
    insights,
    batteryReservePercent: selected.dossier.batteryReservePercent,
    tariffPlan: selected.dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
  });
  const nextSolarAt = adaptiveForecast.prudentSlots.find((slot) =>
    Date.parse(slot.startsAt) > now.getTime() && slot.estimatedWh >= 100)?.startsAt ?? null;
  const batteryOutlook = buildBatteryNightOutlook({
    now,
    batteryCapacityWh: selected.dossier.batteryCapacityWh,
    batteryPercent: current.batteryPercent,
    reservePercent: selected.dossier.batteryReservePercent,
    currentDischargeWatts: current.batteryWatts,
    history,
    nextSolarAt,
  });
  return {
    dossier: {
      id: selected.dossier.id,
      publicId: selected.dossier.publicId,
      name: selected.dossier.customerName,
      batteryCapacityWh: selected.dossier.batteryCapacityWh,
      batteryReservePercent: selected.dossier.batteryReservePercent,
    },
    tariff: {
      plan: selected.dossier.tariffPlan === "hp_hc" ? "hp_hc" as const : "base" as const,
      offPeakPeriods: offPeakPeriodsFrom(selected.dossier.offPeakPeriodsJson),
      prices: {
        baseMilliEurosPerKwh: selected.dossier.basePriceMilliEurosPerKwh,
        peakMilliEurosPerKwh: selected.dossier.peakPriceMilliEurosPerKwh,
        offPeakMilliEurosPerKwh: selected.dossier.offPeakPriceMilliEurosPerKwh,
        exportMilliEurosPerKwh: selected.dossier.exportPriceMilliEurosPerKwh,
      },
      pricesConfigured: selected.dossier.tariffPlan === "hp_hc"
        ? selected.dossier.peakPriceMilliEurosPerKwh != null && selected.dossier.offPeakPriceMilliEurosPerKwh != null
        : selected.dossier.basePriceMilliEurosPerKwh != null,
    },
    equipmentCapabilities,
    current,
    historySamples: history.length,
    week,
    actionPlan,
    batteryOutlook,
    solarForecast: {
      available: forecast.length > 0,
      source: "Prévision météo locale",
      slots: adaptiveForecast.prudentSlots.slice(0, 24),
      rawSlots: adaptiveForecast.rawSlots.slice(0, 24),
      rawTodayWh: adaptiveForecast.rawTodayWh,
      prudentTodayWh: adaptiveForecast.prudentTodayWh,
      rawRemainingWh: adaptiveForecast.rawRemainingWh,
      prudentRemainingWh: adaptiveForecast.prudentRemainingWh,
      correctionPercent: adaptiveForecast.correctionPercent,
      confidence: adaptiveForecast.confidence,
      explanation: adaptiveForecast.explanation,
    },
    predictivePlan,
    predictivePlans,
    consumptionBreakdown,
    insights,
  };
}

export async function consumeAssistantRequest(
  dossierId: number,
  kind: AssistantQuotaKind,
  now = new Date(),
) {
  const month = assistantQuotaBucket(kind, now);
  const db = getDb();
  const [usage] = await db.insert(assistantUsage).values({
    dossierId,
    month,
    requestCount: 1,
    updatedAt: now.toISOString(),
  }).onConflictDoUpdate({
    target: [assistantUsage.dossierId, assistantUsage.month],
    set: {
      requestCount: sql`${assistantUsage.requestCount} + 1`,
      updatedAt: now.toISOString(),
    },
    setWhere: lt(assistantUsage.requestCount, ASSISTANT_MONTHLY_LIMIT),
  }).returning({ requestCount: assistantUsage.requestCount });
  return Boolean(usage && assistantQuotaAllows(usage.requestCount - 1));
}

export async function refundAssistantRequest(
  dossierId: number,
  kind: AssistantQuotaKind,
  now = new Date(),
) {
  const month = assistantQuotaBucket(kind, now);
  await getDb().update(assistantUsage).set({
    requestCount: sql`${assistantUsage.requestCount} - 1`,
    updatedAt: now.toISOString(),
  }).where(and(
    eq(assistantUsage.dossierId, dossierId),
    eq(assistantUsage.month, month),
    gt(assistantUsage.requestCount, 0),
  ));
}
