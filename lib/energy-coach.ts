import { and, desc, eq, gte, sql } from "drizzle-orm";
import { getDb } from "../db";
import { assistantUsage, energySnapshots } from "../db/schema";
import { selectAgentForDossier } from "./agent-home";

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

const bindings = {
  solarWatts: ["sensor.inverter_pv_power", "sensor.onduleur_pv_power", "input_number.demo_solar_power"],
  homeWatts: ["sensor.inverter_load_power", "sensor.onduleur_load_power", "input_number.demo_house_power"],
  gridWatts: ["sensor.inverter_grid_power", "sensor.onduleur_grid_power", "sensor.1_2_3_home_puissance_reseau"],
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
