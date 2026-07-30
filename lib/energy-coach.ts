import { and, desc, eq, gte, sql } from "drizzle-orm";
import { getDb } from "../db";
import { assistantUsage, energySnapshots } from "../db/schema";
import { selectAgentForDossier } from "./agent-home";
import {
  buildAdaptiveSolarForecast,
  buildPredictiveEnergyPlan,
  type SolarForecastSlot,
} from "./predictive-energy";

export type EnergyInventoryItem = {
  entityId: string;
  name: string;
  domain: string;
  state: string;
  deviceClass?: string | null;
};

export type EnergySnapshotValues = {
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

export type EnergyInsight = {
  id: string;
  icon: string;
  tone: "positive" | "attention" | "tip";
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
};

const bindings = {
  solarWatts: ["sensor.inverter_pv_power", "sensor.onduleur_pv_power", "input_number.demo_solar_power"],
  homeWatts: [
    "sensor.shellyem3_483fdac38616_channel_b_power",
    "sensor.inverter_load_power",
    "sensor.onduleur_load_power",
    "input_number.demo_house_power",
  ],
  gridWatts: [
    "sensor.shellyem3_483fdac38616_channel_c_power",
    "sensor.inverter_grid_power",
    "sensor.onduleur_grid_power",
    "sensor.1_2_3_home_puissance_reseau",
  ],
  batteryPercent: ["sensor.inverter_battery", "sensor.onduleur_battery", "input_number.demo_battery_soc"],
  batteryWatts: ["sensor.inverter_battery_power", "sensor.onduleur_battery_power", "sensor.1_2_3_home_puissance_batterie"],
  filtrationWatts: ["sensor.filtration_piscine_puissance"],
  hotWaterWatts: ["sensor.1_2_3_home_puissance_chauffe_eau"],
  vehicleWatts: [
    "sensor.tesla_model_x_charger_power",
    "sensor.tesla_y_charger_power",
    "input_number.demo_tesla_charge_power",
  ],
  dailyProductionWh: ["sensor.inverter_today_production", "sensor.onduleur_today_production"],
  dailyConsumptionWh: ["sensor.inverter_today_load_consumption", "sensor.onduleur_today_load_consumption"],
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
  poolTemperature: ["input_number.demo_pool_temperature"],
  poolSetpoint: ["input_number.demo_pool_setpoint"],
  poolHeatPump: ["input_boolean.demo_pool_heat_pump"],
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
  const item = ids.map((id) => inventory.find((candidate) => candidate.entityId === id))
    .find(Boolean);
  const value = Number(item?.state);
  return Number.isFinite(value) ? value : 0;
}

function nullableNumberFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = ids.map((id) => inventory.find((candidate) => candidate.entityId === id))
    .find(Boolean);
  const value = Number(item?.state);
  return Number.isFinite(value) ? value : null;
}

function activeFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = ids.map((id) => inventory.find((candidate) => candidate.entityId === id))
    .find(Boolean);
  return Boolean(item && ["on", "heat", "heating"].includes(item.state.toLowerCase()));
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

function loadState(
  load: FlexibleLoadConfiguration,
  inventory: EnergyInventoryItem[],
  current: EnergySnapshotValues,
) {
  if (load.category === "pool") {
    const temperature = nullableNumberFrom(inventory, bindings.poolTemperature);
    const setpoint = nullableNumberFrom(inventory, bindings.poolSetpoint);
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

function integer(value: number) {
  return Math.round(Math.max(-100_000, Math.min(100_000, value)));
}

export function energySnapshotFromInventory(
  inventory: EnergyInventoryItem[],
): EnergySnapshotValues {
  return {
    solarWatts: integer(numberFrom(inventory, bindings.solarWatts)),
    homeWatts: integer(numberFrom(inventory, bindings.homeWatts)),
    gridWatts: integer(numberFrom(inventory, bindings.gridWatts)),
    batteryPercent: integer(numberFrom(inventory, bindings.batteryPercent)),
    batteryWatts: integer(numberFrom(inventory, bindings.batteryWatts)),
    filtrationWatts: integer(numberFrom(inventory, bindings.filtrationWatts)),
    hotWaterWatts: integer(numberFrom(inventory, bindings.hotWaterWatts)),
    vehicleWatts: integer(numberFrom(inventory, bindings.vehicleWatts)),
    dailyProductionWh: integer(numberFrom(inventory, bindings.dailyProductionWh) * 1000),
    dailyConsumptionWh: integer(numberFrom(inventory, bindings.dailyConsumptionWh) * 1000),
  };
}

export function fifteenMinuteBucket(date: Date) {
  const minutes = Math.floor(date.getUTCMinutes() / 15) * 15;
  const bucket = new Date(date);
  bucket.setUTCMinutes(minutes, 0, 0);
  return bucket.toISOString();
}

function average(values: number[]) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function euro(value: number) {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Math.max(0, value));
}

function energyInsights(
  current: EnergySnapshotValues,
  history: Array<typeof energySnapshots.$inferSelect>,
): EnergyInsight[] {
  const insights: EnergyInsight[] = [];
  const nightSamples = history.filter((sample) => {
    const hour = new Date(sample.capturedAt).getUTCHours();
    return hour >= 0 && hour < 5;
  });
  const nightBase = average(nightSamples.map((sample) => sample.homeWatts));
  if (nightBase >= 250) {
    const avoidableWatts = Math.max(0, nightBase - 150);
    const monthlySaving = avoidableWatts * 8 * 30 / 1000 * 0.25;
    insights.push({
      id: "night-base",
      icon: "☾",
      tone: "attention",
      title: "Consommation nocturne à examiner",
      description: `La maison consomme en moyenne ${Math.round(nightBase)} W pendant la nuit.`,
      impact: `Jusqu’à ${euro(monthlySaving)} / mois estimés`,
      action: "Identifier les appareils en veille",
    });
  }

  const likelySurplus = Math.max(0, current.solarWatts - current.homeWatts);
  if (likelySurplus >= 500 && current.batteryPercent >= 85) {
    insights.push({
      id: "solar-surplus",
      icon: "☀",
      tone: "positive",
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
      title: "Réserve batterie faible",
      description: `La batterie est à ${current.batteryPercent} %.`,
      impact: "Garder une réserve pour le soir",
      action: "Vérifier la stratégie de batterie",
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
      title: "Analyse en cours",
      description: "Le coach collecte progressivement les habitudes de la maison.",
      impact: "Premiers conseils après quelques heures",
      action: "Poser une question au coach",
    });
  }
  return insights.slice(0, 4);
}

export async function getEnergyCoachContext(dossierPublicId?: string | null) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const current = energySnapshotFromInventory(inventory);
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const history = await getDb().select().from(energySnapshots)
    .where(and(
      eq(energySnapshots.dossierId, selected.dossier.id),
      gte(energySnapshots.capturedAt, since),
    ))
    .orderBy(desc(energySnapshots.capturedAt))
    .limit(700);
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
      sample.hotWaterWatts -
      sample.vehicleWatts,
    )
  ).filter((value) => value > 0);
  const currentBaseLoad = Math.max(
    0,
    current.homeWatts -
    current.filtrationWatts -
    current.hotWaterWatts -
    current.vehicleWatts,
  );
  const baseLoadWatts = Math.round(Math.max(
    150,
    baseSamples.length ? average(baseSamples.slice(0, 192)) : currentBaseLoad,
  ));
  const configuredLoads = flexibleLoadsFrom(selected.dossier.flexibleLoadsJson)
    .filter((load) => load.enabled)
    .sort((left, right) => left.priority - right.priority);
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
  for (const sample of history) {
    const day = sample.capturedAt.slice(0, 10);
    const previous = daily.get(day) ?? { productionWh: 0, consumptionWh: 0 };
    daily.set(day, {
      productionWh: Math.max(previous.productionWh, sample.dailyProductionWh),
      consumptionWh: Math.max(previous.consumptionWh, sample.dailyConsumptionWh),
    });
  }
  const week = Array.from(daily.values()).reduce((total, day) => ({
    productionWh: total.productionWh + day.productionWh,
    consumptionWh: total.consumptionWh + day.consumptionWh,
  }), { productionWh: 0, consumptionWh: 0 });
  return {
    dossier: {
      id: selected.dossier.id,
      publicId: selected.dossier.publicId,
      name: selected.dossier.customerName,
    },
    current,
    historySamples: history.length,
    week,
    solarForecast: {
      available: forecast.length > 0,
      source: "Open-Meteo via Home Assistant",
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
    insights: energyInsights(current, history),
  };
}

export async function consumeAssistantRequest(dossierId: number) {
  const month = new Date().toISOString().slice(0, 7);
  const db = getDb();
  const [usage] = await db.select().from(assistantUsage)
    .where(and(
      eq(assistantUsage.dossierId, dossierId),
      eq(assistantUsage.month, month),
    )).limit(1);
  if ((usage?.requestCount ?? 0) >= 100) return false;
  await db.insert(assistantUsage).values({
    dossierId,
    month,
    requestCount: 1,
    updatedAt: new Date().toISOString(),
  }).onConflictDoUpdate({
    target: [assistantUsage.dossierId, assistantUsage.month],
    set: {
      requestCount: sql`${assistantUsage.requestCount} + 1`,
      updatedAt: new Date().toISOString(),
    },
  });
  return true;
}
