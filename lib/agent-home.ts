import { and, asc, desc, eq, gte, lt } from "drizzle-orm";
import { getDb } from "../db";
import { agentBoxes, agentCommands, energySnapshots, installationDossiers } from "../db/schema";
import { relayHouseIdForDossier } from "./relay-house";
import { ENERGY_PROFILE } from "./energy-profile.generated";
import { HOUSE_BINDINGS } from "./house-bindings.generated";
import {
  normalizeEntityText,
  resolveEntityCandidate,
} from "./entity-resolution.generated.js";
import {
  allocateHomeAndVehiclePower,
  energyValueKwh,
  formatKwh,
  formatWatts,
  powerValueWatts,
} from "./energy-allocation.generated.js";
import { dailySolarPeakWatts } from "./daily-solar-peak.generated.js";
import { agentConnectionHealth } from "./connection-health.js";
import { normalizeEnabledModules } from "./client-modules.js";
import { subscriptionSummary } from "./subscription";

type InventoryItem = {
  entityId: string;
  name: string;
  domain: string;
  state: string;
  deviceClass?: string | null;
  attributes?: Record<string, unknown>;
};

type ControlBinding = {
  entityIds: readonly string[];
  label: string;
  icon: string;
  room: string;
  category: string;
  controllable?: boolean;
};

type RingSecurityBinding = {
  cameraEntityId: string;
  motionDetectionEntityId: string;
  lastActivityEntityId: string;
  batteryEntityId?: string;
  label: string;
  room: string;
  kind: "camera" | "doorbell";
};

type PortalDevice = {
  publicId: string;
  name: string;
  room: string;
  areaPublicId: string;
  category: string;
  state: string;
  available: boolean;
  controllable: boolean;
  battery: number | null;
  visible: boolean;
  lastChanged: string;
};

const ringSecurityBindings: RingSecurityBinding[] = [
  {
    cameraEntityId: "camera.batiment_live_view",
    motionDetectionEntityId: "switch.batiment_motion_detection",
    lastActivityEntityId: "sensor.batiment_derniere_activite",
    batteryEntityId: "sensor.batiment_batterie",
    label: "Sonnette bâtiment",
    room: "Entrée",
    kind: "doorbell",
  },
  {
    cameraEntityId: "camera.preparation_1_live_view",
    motionDetectionEntityId: "switch.preparation_1_motion_detection",
    lastActivityEntityId: "sensor.preparation_1_derniere_activite",
    label: "Caméra Préparation 1",
    room: "Préparation",
    kind: "camera",
  },
];

function ringCameraAssignments(): Record<string, string> {
  try {
    const parsed = JSON.parse(process.env.RING_CAMERA_ASSIGNMENTS_JSON ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([displayReference, sourceReference]) =>
          displayReference.length > 0 &&
          typeof sourceReference === "string" &&
          sourceReference.length > 0
        )
        .map(([displayReference, sourceReference]) => [
          displayReference,
          String(sourceReference),
        ]),
    );
  } catch {
    return {};
  }
}

const controlBindings: ControlBinding[] = [
  {
    entityIds: [...HOUSE_BINDINGS.heatingClimate, "input_boolean.demo_heating"],
    label: "Chauffage", icon: "♨", room: "Maison", category: "Confort",
  },
  {
    entityIds: [...HOUSE_BINDINGS.filtration, "input_boolean.demo_pool_filtration"],
    label: "Filtration", icon: "≋", room: "Piscine", category: "Piscine",
  },
  {
    entityIds: [...HOUSE_BINDINGS.poolHeatPump, "input_boolean.demo_pool_heat_pump"],
    label: "PAC piscine", icon: "♨", room: "Piscine", category: "Piscine",
  },
  {
    entityIds: ["lock.accueil", "lock.nuki", "input_boolean.demo_nuki_locked"],
    label: "Serrure Nuki", icon: "▣", room: "Entrée", category: "Sécurité",
  },
  {
    entityIds: [
      "camera.batiment_live_view",
      "camera.preparation_1_live_view",
      "camera.terrasse_maison_live_view",
      "camera.portail_maison_live_view",
      "input_boolean.demo_camera_surveillance",
    ],
    label: "Caméras", icon: "◉", room: "Extérieur", category: "Sécurité",
    controllable: false,
  },
  {
    entityIds: [...HOUSE_BINDINGS.waterHeater, "input_boolean.chauffe_eau_shelly"],
    label: "Ballon d’eau chaude", icon: "♨", room: "Local technique", category: "Eau chaude",
  },
  {
    entityIds: HOUSE_BINDINGS.gate,
    label: "Portail", icon: "▣", room: "Extérieur", category: "Accès",
  },
  {
    entityIds: HOUSE_BINDINGS.terrace,
    label: "Terrasse", icon: "☀", room: "Extérieur", category: "Éclairage",
  },
  {
    entityIds: HOUSE_BINDINGS.poolLight,
    label: "Éclairage piscine", icon: "◉", room: "Piscine", category: "Piscine",
  },
  {
    entityIds: HOUSE_BINDINGS.teslaModelXClimate,
    label: "Climatisation Tesla", icon: "❄", room: "Garage", category: "Véhicule",
  },
  {
    entityIds: HOUSE_BINDINGS.teslaModelXCharger,
    label: "Recharge Tesla", icon: "ϟ", room: "Garage", category: "Véhicule",
  },
  {
    entityIds: HOUSE_BINDINGS.teslaModelXDoors,
    label: "Portières Tesla", icon: "▣", room: "Garage", category: "Véhicule",
  },
  {
    entityIds: HOUSE_BINDINGS.teslaModelXChargerDoor,
    label: "Trappe Tesla", icon: "◉", room: "Garage", category: "Véhicule",
  },
  {
    entityIds: HOUSE_BINDINGS.teslaModelXSentry,
    label: "Mode Sentinelle", icon: "⬡", room: "Garage", category: "Véhicule",
  },
];

const valueBindings = {
  solar: [...ENERGY_PROFILE.solarPower, "input_number.demo_solar_power"],
  home: [...ENERGY_PROFILE.homePower, "input_number.demo_house_power"],
  grid: ENERGY_PROFILE.gridPower,
  battery: [...ENERGY_PROFILE.batteryLevel, "input_number.demo_battery_soc"],
  batteryPower: ENERGY_PROFILE.batteryPower,
  dailyProduction: ENERGY_PROFILE.dailyProduction,
  dailyConsumption: ENERGY_PROFILE.dailyConsumption,
  dailyImport: ENERGY_PROFILE.dailyImport,
  dailyExport: ENERGY_PROFILE.dailyExport,
  monthlyProduction: ENERGY_PROFILE.monthlyProduction,
  monthlyConsumption: ENERGY_PROFILE.monthlyConsumption,
  monthlyImport: ENERGY_PROFILE.monthlyImport,
  monthlyExport: ENERGY_PROFILE.monthlyExport,
  yearlyProduction: ENERGY_PROFILE.yearlyProduction,
  yearlyConsumption: ENERGY_PROFILE.yearlyConsumption,
  yearlyImport: ENERGY_PROFILE.yearlyImport,
  yearlyExport: ENERGY_PROFILE.yearlyExport,
  installedPower: ENERGY_PROFILE.installedPower,
  pv1: ENERGY_PROFILE.pv1,
  pv2: ENERGY_PROFILE.pv2,
  pv3: ENERGY_PROFILE.pv3,
  peakPower: ENERGY_PROFILE.peakPower,
  forecastToday: ENERGY_PROFILE.forecastToday,
  forecastRemaining: ENERGY_PROFILE.forecastRemaining,
  forecastPowerNow: ENERGY_PROFILE.forecastPowerNow,
  cloudCover: ENERGY_PROFILE.cloudCover,
  moonPhase: ENERGY_PROFILE.moonPhase,
  filtration: HOUSE_BINDINGS.filtrationPower,
  filtrationToday: ["sensor.1_2_3_home_filtration_energy_today"],
  poolHeatPumpPower: HOUSE_BINDINGS.poolHeatPumpPower,
  poolHeatPumpToday: ["sensor.1_2_3_home_pool_heat_pump_energy_today"],
  poolAirTemperature: HOUSE_BINDINGS.poolAirTemperature,
  poolPh: HOUSE_BINDINGS.poolPh,
  poolChlorine: HOUSE_BINDINGS.poolChlorine,
  hotWaterPower: HOUSE_BINDINGS.waterHeaterPower,
  hotWaterToday: ["sensor.1_2_3_home_water_heater_energy_today"],
  hotWaterAvailable: ["sensor.1_2_3_home_eau_chaude_disponible"],
  hotWaterTemperature: ["input_number.chauffe_eau_temperature"],
  hotWaterMode: ["input_select.chauffe_eau_mode"],
  indoorTemperature: [...HOUSE_BINDINGS.livingRoomTemperature, "input_number.demo_indoor_temperature"],
  bedroomTemperature: HOUSE_BINDINGS.bedroomTemperature,
  heatingSetpoint: [...HOUSE_BINDINGS.heatingClimate, "input_number.demo_heating_setpoint"],
  poolTemperature: [...HOUSE_BINDINGS.poolWaterTemperature, "input_number.demo_pool_temperature"],
  poolSetpoint: ["input_number.demo_pool_setpoint"],
  teslaBattery: [...HOUSE_BINDINGS.teslaModelXBattery, "input_number.demo_tesla_soc"],
  teslaPower: [...HOUSE_BINDINGS.teslaModelXChargerPower, "input_number.demo_tesla_charge_power"],
  teslaPlugged: HOUSE_BINDINGS.teslaModelXPlugged,
  teslaRange: HOUSE_BINDINGS.teslaModelXRange,
  teslaCabinTemperature: HOUSE_BINDINGS.teslaModelXCabinTemperature,
  teslaOnline: HOUSE_BINDINGS.teslaModelXOnline,
  teslaCharging: HOUSE_BINDINGS.teslaModelXCharging,
  teslaDoors: HOUSE_BINDINGS.teslaModelXDoors,
  teslaClimate: HOUSE_BINDINGS.teslaModelXClimate,
  teslaSentry: HOUSE_BINDINGS.teslaModelXSentry,
  lektricoPower: HOUSE_BINDINGS.lektricoPower,
  lektricoState: HOUSE_BINDINGS.lektricoState,
  lektricoEnergy: HOUSE_BINDINGS.lektricoEnergy,
  lektricoCurrent: HOUSE_BINDINGS.lektricoCurrent,
  lektricoVoltage: HOUSE_BINDINGS.lektricoVoltage,
  lektricoTemperature: HOUSE_BINDINGS.lektricoTemperature,
  lektricoDynamicLimit: HOUSE_BINDINGS.lektricoDynamicLimit,
  lektricoLimitReason: HOUSE_BINDINGS.lektricoLimitReason,
  demoMode: ["input_select.demo_mode"],
} as const;

const showroomOnlyEntityIds = new Set([
  "input_boolean.demo_heating",
  "input_boolean.demo_pool_filtration",
  "input_boolean.demo_pool_heat_pump",
  "input_boolean.demo_nuki_locked",
  "input_boolean.demo_camera_surveillance",
  "input_boolean.chauffe_eau_shelly",
  "input_number.demo_solar_power",
  "input_number.demo_house_power",
  "input_number.demo_battery_soc",
  "input_number.demo_indoor_temperature",
  "input_number.demo_heating_setpoint",
  "input_number.demo_pool_temperature",
  "input_number.demo_pool_setpoint",
  "input_number.demo_tesla_soc",
  "input_number.demo_tesla_charge_power",
  "input_select.demo_mode",
]);

function publicId(value: string, prefix = "appareil") {
  let hash = 2166136261;
  for (const char of value) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${prefix}_${(hash >>> 0).toString(36)}`;
}

function parseInventory(value: string): InventoryItem[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item): item is InventoryItem =>
      Boolean(item && typeof item.entityId === "string" && typeof item.state === "string")
    ) : [];
  } catch {
    return [];
  }
}

function normalized(value: string) {
  return normalizeEntityText(value);
}

function find(inventory: InventoryItem[], ids: readonly string[]) {
  const candidate = resolveEntityCandidate(inventory.map((item) => ({
    item,
    entityId: item.entityId,
    name: item.name,
    deviceClass: typeof item.attributes?.device_class === "string"
      ? item.attributes.device_class
      : "",
    state: item.state,
  })), ids);
  return candidate?.item ?? null;
}

function attributeNumber(item: InventoryItem | null, key: string) {
  const value = item?.attributes?.[key];
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formattedAttribute(item: InventoryItem | null, key: string, unit: string) {
  const value = attributeNumber(item, key);
  return value === null ? "—" : `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(value)} ${unit}`;
}

function formatted(item: InventoryItem | null, unit: string, fallback = "—") {
  if (!item || ["unknown", "unavailable"].includes(item.state)) return fallback;
  const numeric = Number(item.state);
  if (!Number.isFinite(numeric)) return item.state;
  const measuredUnit = typeof item.attributes?.unit_of_measurement === "string"
    ? item.attributes.unit_of_measurement.trim()
    : "";
  const displayedUnit = measuredUnit || unit;
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(numeric)}${displayedUnit ? ` ${displayedUnit}` : ""}`;
}

function inventoryPowerWatts(item: InventoryItem | null, fallbackUnit = "W") {
  if (!item || ["unknown", "unavailable"].includes(item.state.toLowerCase())) return 0;
  const measuredUnit = typeof item.attributes?.unit_of_measurement === "string"
    ? item.attributes.unit_of_measurement
    : fallbackUnit;
  return powerValueWatts(item.state, measuredUnit);
}

function formattedPower(item: InventoryItem | null, fallback = "0 W", fallbackUnit = "W") {
  if (!item || ["unknown", "unavailable"].includes(item.state.toLowerCase())) return fallback;
  return formatWatts(inventoryPowerWatts(item, fallbackUnit));
}

function inventoryEnergyKwh(item: InventoryItem | null) {
  if (!item || ["unknown", "unavailable"].includes(item.state.toLowerCase())) return null;
  return energyValueKwh(item.state, String(item.attributes?.unit_of_measurement || "kWh"));
}

function formattedEnergy(item: InventoryItem | null, fallback = "—") {
  const value = inventoryEnergyKwh(item);
  return value === null
    ? fallback
    : formatKwh(value, fallback);
}

function derivedEnergyMetrics(
  production: InventoryItem | null,
  consumption: InventoryItem | null,
  imported: InventoryItem | null,
  exported: InventoryItem | null,
) {
  const productionKwh = inventoryEnergyKwh(production);
  const consumptionKwh = inventoryEnergyKwh(consumption);
  const importedKwh = inventoryEnergyKwh(imported);
  const exportedKwh = inventoryEnergyKwh(exported);
  const selfConsumedKwh = productionKwh === null
    ? null
    : Math.max(0, productionKwh - (exportedKwh ?? 0));
  const selfConsumption = productionKwh && selfConsumedKwh !== null
    ? Math.min(100, selfConsumedKwh / productionKwh * 100)
    : productionKwh === 0 ? 0 : null;
  const autonomy = consumptionKwh && importedKwh !== null
    ? Math.max(0, Math.min(100, (consumptionKwh - importedKwh) / consumptionKwh * 100))
    : consumptionKwh === 0 ? 0 : null;
  return {
    selfConsumed: selfConsumedKwh === null
      ? "—"
      : `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(selfConsumedKwh)} kWh`,
    selfConsumption: selfConsumption === null ? "—" : `${Math.round(selfConsumption)} %`,
    autonomy: autonomy === null ? "—" : `${Math.round(autonomy)} %`,
    savings: selfConsumedKwh === null ? "—" : `${(selfConsumedKwh * 0.194).toFixed(2).replace(".", ",")} €`,
    co2Avoided: productionKwh === null ? "—" : `${(productionKwh * 0.055).toFixed(1).replace(".", ",")} kg`,
  };
}

function active(item: InventoryItem | null) {
  return Boolean(item && ["on", "open", "heat", "heating", "locked"].includes(item.state.toLowerCase()));
}

function recentActivity(item: InventoryItem | null) {
  if (!item || ["unknown", "unavailable"].includes(item.state.toLowerCase())) {
    return "Aucune activité récente";
  }
  const timestamp = Date.parse(item.state);
  if (!Number.isFinite(timestamp)) return item.state;
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  }).format(timestamp);
}

function scopedFind(
  inventory: InventoryItem[],
  ids: readonly string[],
  allowShowroomEntities: boolean,
) {
  return find(
    inventory,
    allowShowroomEntities
      ? ids
      : ids.filter((entityId) => !showroomOnlyEntityIds.has(entityId)),
  );
}

function resolvedControl(
  inventory: InventoryItem[],
  binding: ControlBinding,
  allowShowroomEntities: boolean,
) {
  return scopedFind(inventory, binding.entityIds, allowShowroomEntities);
}

export async function selectAgentForDossier(dossierPublicId?: string | null) {
  const defaultDossierReference =
    process.env.DEFAULT_CLIENT_DOSSIER_REFERENCE?.trim();
  if (dossierPublicId || defaultDossierReference) {
    const [dossier] = await getDb().select().from(installationDossiers)
      .where(dossierPublicId
        ? eq(installationDossiers.publicId, dossierPublicId)
        : eq(installationDossiers.reference, defaultDossierReference as string)
      ).limit(1);
    if (dossier) {
      const [agent] = await getDb().select().from(agentBoxes)
        .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
      if (agent) return { agent, dossier };
    }
  }
  const agents = await getDb().select().from(agentBoxes)
    .orderBy(desc(agentBoxes.lastSeenAt)).limit(20);
  const agent = agents.find((candidate) => {
    const inventory = parseInventory(candidate.inventoryJson);
    return controlBindings.some((binding) =>
      binding.entityIds.some((entityId) =>
        inventory.some((item) => item.entityId === entityId)
      )
    );
  }) ?? agents[0];
  if (!agent) return null;
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.id, agent.dossierId)).limit(1);
  return dossier ? { agent, dossier } : null;
}

function parisMidnightUtc(dateKey: string) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const nominalUtc = Date.UTC(year, month - 1, day);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(nominalUtc));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const representedUtc = Date.UTC(
    Number(values.year), Number(values.month) - 1, Number(values.day),
    Number(values.hour), Number(values.minute), Number(values.second),
  );
  return new Date(nominalUtc - (representedUtc - nominalUtc));
}

function parisDateKey(value: Date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export async function getAgentEnergyHistory(
  dossierPublicId: string | null | undefined,
  dateKey: string,
) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) throw new Error("INVALID_DATE");
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const start = parisMidnightUtc(dateKey);
  const nextDate = new Date(start.getTime() + 36 * 60 * 60 * 1000);
  const nextKey = parisDateKey(nextDate);
  const end = parisMidnightUtc(nextKey);
  return getDb().select().from(energySnapshots).where(and(
    eq(energySnapshots.dossierId, selected.dossier.id),
    gte(energySnapshots.capturedAt, start.toISOString()),
    lt(energySnapshots.capturedAt, end.toISOString()),
  )).orderBy(asc(energySnapshots.capturedAt));
}

async function selectRingSourceForDossier(
  selected: NonNullable<Awaited<ReturnType<typeof selectAgentForDossier>>>,
) {
  const assignments = ringCameraAssignments();
  const sourceReference = assignments[selected.dossier.reference];
  if (!sourceReference) {
    return Object.values(assignments).includes(selected.dossier.reference)
      ? null
      : selected;
  }
  if (sourceReference === selected.dossier.reference) return selected;
  const [sourceDossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.reference, sourceReference)).limit(1);
  if (!sourceDossier) return null;
  const [sourceAgent] = await getDb().select().from(agentBoxes)
    .where(eq(agentBoxes.dossierId, sourceDossier.id)).limit(1);
  return sourceAgent ? { agent: sourceAgent, dossier: sourceDossier } : null;
}

export async function getAgentPortalHome(dossierPublicId?: string | null) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const ringSource = await selectRingSourceForDossier(selected);
  const ringInventory = ringSource
    ? parseInventory(ringSource.agent.inventoryJson)
    : [];
  const cameraPlacementReassigned =
    !ringSource &&
    Object.values(ringCameraAssignments()).includes(selected.dossier.reference);
  const allowShowroomEntities =
    selected.dossier.reference.toUpperCase().includes("SHOWROOM");
  const connection = agentConnectionHealth(selected.agent.lastSeenAt);
  const online = connection.connected;
  const ringOnline = Boolean(
    ringSource?.agent.lastSeenAt &&
    Date.now() - Date.parse(ringSource.agent.lastSeenAt) < 120_000
  );
  const offPeakPeriods = (() => {
    try {
      const parsed = JSON.parse(selected.dossier.offPeakPeriodsJson);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  })();

  const ringSecurity = ringSecurityBindings.flatMap((binding) => {
    const camera = ringInventory.find((item) => item.entityId === binding.cameraEntityId);
    if (!camera) return [];
    const motionDetection = ringInventory.find(
      (item) => item.entityId === binding.motionDetectionEntityId,
    ) ?? null;
    const lastActivity = ringInventory.find(
      (item) => item.entityId === binding.lastActivityEntityId,
    ) ?? null;
    const battery = binding.batteryEntityId
      ? ringInventory.find((item) => item.entityId === binding.batteryEntityId) ?? null
      : null;
    const batteryValue = battery && Number.isFinite(Number(battery.state))
      ? Number(battery.state)
      : null;
    const available = ringOnline &&
      !["unknown", "unavailable"].includes(camera.state.toLowerCase());
    return [{
      publicId: publicId(camera.entityId, "securite"),
      label: binding.label,
      room: binding.room,
      kind: binding.kind,
      available,
      battery: batteryValue,
      motionDetectionEnabled: motionDetection?.state.toLowerCase() === "on",
      lastActivity: recentActivity(lastActivity),
    }];
  });

  const controls = controlBindings
    .filter((binding) =>
      binding.label !== "Caméras" ||
      (ringSecurity.length === 0 && !cameraPlacementReassigned)
    )
    .map((binding) => {
    const item = resolvedControl(inventory, binding, allowShowroomEntities);
    const entityId = item?.entityId ?? binding.entityIds[0];
    return {
      publicId: publicId(entityId, "commande"),
      label: binding.label,
      icon: binding.icon,
      active: active(item),
      available: online && Boolean(item) && !["unknown", "unavailable"].includes(item.state),
      controllable: binding.controllable !== false,
    };
  });

  const devices: PortalDevice[] = controlBindings
    .filter((binding) =>
      binding.label !== "Caméras" ||
      (ringSecurity.length === 0 && !cameraPlacementReassigned)
    )
    .map((binding) => {
    const item = resolvedControl(inventory, binding, allowShowroomEntities);
    const entityId = item?.entityId ?? binding.entityIds[0];
    const available = online && Boolean(item) && !["unknown", "unavailable"].includes(item.state);
    return {
      publicId: publicId(entityId),
      name: binding.label,
      room: binding.room,
      areaPublicId: publicId(binding.room, "piece"),
      category: binding.category,
      state: available ? active(item) ? "on" : "off" : "unavailable",
      available,
      controllable: binding.controllable !== false,
      battery: null,
      visible: true,
      lastChanged: selected.agent.lastSeenAt ?? new Date(0).toISOString(),
    };
  });

  for (const ringDevice of ringSecurity) {
    devices.push({
      publicId: ringDevice.publicId,
      name: ringDevice.label,
      room: ringDevice.room,
      areaPublicId: publicId(ringDevice.room, "piece"),
      category: "Sécurité",
      state: ringDevice.available ? "idle" : "unavailable",
      available: ringDevice.available,
      controllable: false,
      battery: ringDevice.battery,
      visible: true,
      lastChanged: selected.agent.lastSeenAt ?? new Date(0).toISOString(),
    });
  }

  const tesla = scopedFind(
    inventory,
    valueBindings.teslaBattery,
    allowShowroomEntities,
  );
  if (tesla) {
    devices.push({
      publicId: publicId(tesla.entityId),
      name: "Tesla",
      room: "Garage",
      areaPublicId: publicId("Garage", "piece"),
      category: "Véhicule",
      state: tesla.state,
      available: online,
      controllable: false,
      battery: Number.isFinite(Number(tesla.state)) ? Number(tesla.state) : null,
      visible: true,
      lastChanged: selected.agent.lastSeenAt ?? new Date(0).toISOString(),
    });
  }

  const automations = inventory
    .filter((item) => item.domain === "automation" && item.name.startsWith("1.2.3 Home"))
    .map((item) => ({
      publicId: publicId(item.entityId, "regle"),
      name: item.name,
      enabled: item.state === "on",
      lastTriggered: null,
      trigger: "Pilotage énergétique",
      action: "Action gérée par la Green Box",
    }));

  const energyItems = {
    solar: scopedFind(inventory, valueBindings.solar, allowShowroomEntities),
    home: scopedFind(inventory, valueBindings.home, allowShowroomEntities),
    grid: scopedFind(inventory, valueBindings.grid, allowShowroomEntities),
    battery: scopedFind(inventory, valueBindings.battery, allowShowroomEntities),
    batteryPower: scopedFind(inventory, valueBindings.batteryPower, allowShowroomEntities),
    dailyProduction: scopedFind(inventory, valueBindings.dailyProduction, allowShowroomEntities),
    dailyConsumption: scopedFind(inventory, valueBindings.dailyConsumption, allowShowroomEntities),
    dailyImport: scopedFind(inventory, valueBindings.dailyImport, allowShowroomEntities),
    dailyExport: scopedFind(inventory, valueBindings.dailyExport, allowShowroomEntities),
    monthlyProduction: scopedFind(inventory, valueBindings.monthlyProduction, allowShowroomEntities),
    monthlyConsumption: scopedFind(inventory, valueBindings.monthlyConsumption, allowShowroomEntities),
    monthlyImport: scopedFind(inventory, valueBindings.monthlyImport, allowShowroomEntities),
    monthlyExport: scopedFind(inventory, valueBindings.monthlyExport, allowShowroomEntities),
    yearlyProduction: scopedFind(inventory, valueBindings.yearlyProduction, allowShowroomEntities),
    yearlyConsumption: scopedFind(inventory, valueBindings.yearlyConsumption, allowShowroomEntities),
    yearlyImport: scopedFind(inventory, valueBindings.yearlyImport, allowShowroomEntities),
    yearlyExport: scopedFind(inventory, valueBindings.yearlyExport, allowShowroomEntities),
    installedPower: scopedFind(inventory, valueBindings.installedPower, allowShowroomEntities),
    peakPower: scopedFind(inventory, valueBindings.peakPower, allowShowroomEntities),
  };
  const dailyMetrics = derivedEnergyMetrics(
    energyItems.dailyProduction,
    energyItems.dailyConsumption,
    energyItems.dailyImport,
    energyItems.dailyExport,
  );
  const lektricoPower = scopedFind(inventory, valueBindings.lektricoPower, allowShowroomEntities);
  const lektricoState = scopedFind(inventory, valueBindings.lektricoState, allowShowroomEntities);
  const teslaPower = scopedFind(inventory, valueBindings.teslaPower, allowShowroomEntities);
  const lektricoAvailable = Boolean(lektricoPower)
    && !["unknown", "unavailable"].includes(lektricoPower.state.toLowerCase());
  const allocatedPower = allocateHomeAndVehiclePower({
    totalHomeWatts: inventoryPowerWatts(energyItems.home),
    // La borne Lektrico remonte actuellement sa mesure en kW. L'attribut
    // Home Assistant reste prioritaire, et ce repli protège aussi les anciens
    // inventaires enregistrés avant la transmission des unités.
    chargerWatts: inventoryPowerWatts(lektricoPower, "kW"),
    fallbackVehicleWatts: inventoryPowerWatts(teslaPower, "kW"),
    chargerAvailable: lektricoAvailable,
  });
  const recentSolarSnapshots = await getDb().select({
    capturedAt: energySnapshots.capturedAt,
    solarWatts: energySnapshots.solarWatts,
  }).from(energySnapshots).where(and(
    eq(energySnapshots.dossierId, selected.dossier.id),
    gte(energySnapshots.capturedAt, new Date(Date.now() - 30 * 60 * 60 * 1000).toISOString()),
  )).limit(160);
  const peakPowerWatts = dailySolarPeakWatts({
    // Le module JavaScript généré infère [] comme never[] sans déclaration de
    // types ; les éléments transmis respectent bien son contrat runtime.
    samples: recentSolarSnapshots as unknown as never[],
    currentWatts: inventoryPowerWatts(energyItems.solar),
    reportedPeakWatts: inventoryPowerWatts(energyItems.peakPower),
    reportedPeakDate: energyItems.peakPower?.attributes?.date,
  });
  const lektricoStateValue = String(lektricoState?.state || "").trim().toLowerCase();
  const teslaPlugged = scopedFind(inventory, valueBindings.teslaPlugged, allowShowroomEntities);
  const teslaPluggedValue = String(teslaPlugged?.state || "").trim().toLowerCase();
  const vehiclePlugged = allocatedPower.vehicleWatts > 5
    || [lektricoStateValue, teslaPluggedValue].some((state) =>
      ["on", "connected", "charging", "complete", "stopped", "no_power", "starting", "branchée"]
        .some((candidate) => state.includes(candidate))
    );
  const heatingClimate = scopedFind(inventory, valueBindings.heatingSetpoint, allowShowroomEntities);
  const poolClimate = scopedFind(inventory, HOUSE_BINDINGS.poolHeatPump, allowShowroomEntities);
  const weather = inventory.find((item) => item.domain === "weather") ?? null;
  const poolAir = scopedFind(inventory, valueBindings.poolAirTemperature, allowShowroomEntities);
  const effectivePoolAir = poolAir
    ? formatted(poolAir, "°C")
    : formattedAttribute(weather, "temperature", "°C");

  return {
    connected: online,
    connection,
    source: "agent",
    dossier: {
      publicId: selected.dossier.publicId,
      reference: selected.dossier.reference,
      name: selected.dossier.customerName,
    },
    subscription: subscriptionSummary(selected.dossier),
    enabledModules: normalizeEnabledModules(selected.dossier.enabledModules),
    deviceCount: devices.length,
    unavailableCount: devices.filter((device) => !device.available).length,
    lowBatteryCount: devices.filter((device) => device.battery !== null && device.battery < 20).length,
    devices,
    areas: ["Maison", "Entrée", "Piscine", "Extérieur", "Garage", "Local technique"]
      .map((name) => ({ publicId: publicId(name, "piece"), name })),
    automations,
    mobileOverview: {
      // Les libellés de `energy` sont faits pour l'affichage et perdent
      // volontairement le signe. `flow` est la source numérique canonique
      // utilisée par le portail pour conserver le sens import/export et
      // charge/décharge exactement comme dans l'application mobile.
      flow: {
        solarWatts: inventoryPowerWatts(energyItems.solar),
        homeWatts: allocatedPower.homeWatts,
        gridWatts: inventoryPowerWatts(energyItems.grid),
        batteryWatts: inventoryPowerWatts(energyItems.batteryPower),
        vehicleWatts: allocatedPower.vehicleWatts,
        vehiclePlugged,
      },
      energy: {
        solar: formattedPower(energyItems.solar),
        home: formatWatts(allocatedPower.homeWatts),
        grid: formattedPower(energyItems.grid),
        battery: formatted(energyItems.battery, "%", "0 %"),
        batteryPower: formattedPower(energyItems.batteryPower),
        filtration: formattedPower(scopedFind(inventory, valueBindings.filtration, allowShowroomEntities)),
        dailyProduction: formattedEnergy(energyItems.dailyProduction),
        dailyConsumption: formattedEnergy(energyItems.dailyConsumption),
        dailyImport: formattedEnergy(energyItems.dailyImport),
        dailyExport: formattedEnergy(energyItems.dailyExport),
        monthlyProduction: formattedEnergy(energyItems.monthlyProduction),
        monthlyConsumption: formattedEnergy(energyItems.monthlyConsumption),
        monthlyImport: formattedEnergy(energyItems.monthlyImport),
        monthlyExport: formattedEnergy(energyItems.monthlyExport),
        yearlyProduction: formattedEnergy(energyItems.yearlyProduction),
        yearlyConsumption: formattedEnergy(energyItems.yearlyConsumption),
        yearlyImport: formattedEnergy(energyItems.yearlyImport),
        yearlyExport: formattedEnergy(energyItems.yearlyExport),
        installedPower: formatted(energyItems.installedPower, "Wc", "9 635 Wc"),
        vehiclePower: formatWatts(allocatedPower.vehicleWatts),
        pv1: formattedPower(scopedFind(inventory, valueBindings.pv1, allowShowroomEntities)),
        pv2: formattedPower(scopedFind(inventory, valueBindings.pv2, allowShowroomEntities)),
        pv3: formattedPower(scopedFind(inventory, valueBindings.pv3, allowShowroomEntities)),
        peakPower: formatWatts(peakPowerWatts),
        forecastToday: formattedEnergy(scopedFind(inventory, valueBindings.forecastToday, allowShowroomEntities)),
        forecastRemaining: formattedEnergy(scopedFind(inventory, valueBindings.forecastRemaining, allowShowroomEntities)),
        forecastPowerNow: formattedPower(scopedFind(inventory, valueBindings.forecastPowerNow, allowShowroomEntities), "—"),
        cloudCover: formatted(scopedFind(inventory, valueBindings.cloudCover, allowShowroomEntities), "%"),
        moonPhase: formatted(scopedFind(inventory, valueBindings.moonPhase, allowShowroomEntities), ""),
        filtrationToday: formattedEnergy(scopedFind(inventory, valueBindings.filtrationToday, allowShowroomEntities)),
        poolHeatPump: formattedPower(scopedFind(inventory, valueBindings.poolHeatPumpPower, allowShowroomEntities)),
        poolHeatPumpToday: formattedEnergy(scopedFind(inventory, valueBindings.poolHeatPumpToday, allowShowroomEntities)),
        poolPh: formatted(scopedFind(inventory, valueBindings.poolPh, allowShowroomEntities), ""),
        poolChlorine: formatted(scopedFind(inventory, valueBindings.poolChlorine, allowShowroomEntities), ""),
        hotWaterToday: formattedEnergy(scopedFind(inventory, valueBindings.hotWaterToday, allowShowroomEntities)),
        teslaRange: formatted(scopedFind(inventory, valueBindings.teslaRange, allowShowroomEntities), "km"),
        teslaCabinTemperature: formatted(scopedFind(inventory, valueBindings.teslaCabinTemperature, allowShowroomEntities), "°C"),
        lektricoEnergy: formattedEnergy(scopedFind(inventory, valueBindings.lektricoEnergy, allowShowroomEntities)),
        lektricoCurrent: formatted(scopedFind(inventory, valueBindings.lektricoCurrent, allowShowroomEntities), "A"),
        lektricoVoltage: formatted(scopedFind(inventory, valueBindings.lektricoVoltage, allowShowroomEntities), "V"),
        lektricoTemperature: formatted(scopedFind(inventory, valueBindings.lektricoTemperature, allowShowroomEntities), "°C"),
        lektricoDynamicLimit: formatted(scopedFind(inventory, valueBindings.lektricoDynamicLimit, allowShowroomEntities), "A"),
        lektricoLimitReason: formatted(scopedFind(inventory, valueBindings.lektricoLimitReason, allowShowroomEntities), ""),
        ...dailyMetrics,
      },
      controls,
      security: ringSecurity,
      comfort: {
        indoorTemperature: formatted(scopedFind(inventory, valueBindings.indoorTemperature, allowShowroomEntities), "°C"),
        bedroomTemperature: formatted(scopedFind(inventory, valueBindings.bedroomTemperature, allowShowroomEntities), "°C"),
        heatingSetpoint: formattedAttribute(heatingClimate, "temperature", "°C"),
        poolTemperature: formatted(scopedFind(inventory, valueBindings.poolTemperature, allowShowroomEntities), "°C"),
        poolAirTemperature: effectivePoolAir,
        poolSetpoint: formattedAttribute(poolClimate, "temperature", "°C") === "—"
          ? formatted(scopedFind(inventory, valueBindings.poolSetpoint, allowShowroomEntities), "°C")
          : formattedAttribute(poolClimate, "temperature", "°C"),
        hotWaterTemperature: formatted(scopedFind(inventory, valueBindings.hotWaterTemperature, allowShowroomEntities), "°C"),
        hotWaterAvailable: formatted(scopedFind(inventory, valueBindings.hotWaterAvailable, allowShowroomEntities), "%"),
        hotWaterPower: formattedPower(scopedFind(inventory, valueBindings.hotWaterPower, allowShowroomEntities)),
        hotWaterMode: formatted(scopedFind(inventory, valueBindings.hotWaterMode, allowShowroomEntities), ""),
        teslaBattery: formatted(scopedFind(inventory, valueBindings.teslaBattery, allowShowroomEntities), "%"),
        teslaPower: formatWatts(allocatedPower.vehicleWatts),
        teslaPlugged: lektricoState
          ? formatted(lektricoState, "", "off")
          : formatted(teslaPlugged, "", "off"),
        teslaOnline: formatted(scopedFind(inventory, valueBindings.teslaOnline, allowShowroomEntities), "", "off"),
        teslaCharging: formatted(scopedFind(inventory, valueBindings.teslaCharging, allowShowroomEntities), "", "off"),
        teslaDoors: formatted(scopedFind(inventory, valueBindings.teslaDoors, allowShowroomEntities), "", "unknown"),
        teslaClimate: formatted(scopedFind(inventory, valueBindings.teslaClimate, allowShowroomEntities), "", "off"),
        teslaSentry: formatted(scopedFind(inventory, valueBindings.teslaSentry, allowShowroomEntities), "", "off"),
        demoMode: formatted(scopedFind(inventory, valueBindings.demoMode, allowShowroomEntities), ""),
      },
      strategy: {
        tariffPlan: selected.dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
        offPeakPeriods,
      },
    },
  };
}

export async function resolveRingCameraForDossier(
  publicCameraId: string,
  dossierPublicId?: string | null,
) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CAMERA_NOT_FOUND");
  const ringSource = await selectRingSourceForDossier(selected);
  if (!ringSource) throw new Error("CAMERA_NOT_FOUND");
  const inventory = parseInventory(ringSource.agent.inventoryJson);
  const binding = ringSecurityBindings.find((candidate) =>
    publicId(candidate.cameraEntityId, "securite") === publicCameraId
  );
  if (!binding) throw new Error("CAMERA_NOT_FOUND");
  const camera = inventory.find(
    (item) => item.entityId === binding.cameraEntityId,
  );
  if (!camera || ["unknown", "unavailable"].includes(camera.state.toLowerCase())) {
    throw new Error("CAMERA_UNAVAILABLE");
  }
  const online = Boolean(
    ringSource.agent.lastSeenAt &&
    Date.now() - Date.parse(ringSource.agent.lastSeenAt) < 120_000
  );
  if (!online) throw new Error("CAMERA_UNAVAILABLE");
  return {
    entityId: binding.cameraEntityId,
    relayHouseId: relayHouseIdForDossier(ringSource.dossier),
  };
}

export async function queueAgentControl(
  publicControlId: string,
  desiredActive: boolean,
  dossierPublicId?: string | null,
) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const allowShowroomEntities =
    selected.dossier.reference.toUpperCase().includes("SHOWROOM");
  const resolved = controlBindings
    .map((binding) => ({
      binding,
      item: resolvedControl(inventory, binding, allowShowroomEntities),
    }))
    .find(({ item }) =>
      item && publicId(item.entityId, "commande") === publicControlId
    );
  if (!resolved?.item || resolved.binding.controllable === false) {
    throw new Error("CONTROL_NOT_FOUND");
  }
  const domain = resolved.item.entityId.split(".")[0];
  const service = domain === "lock"
    ? desiredActive ? "lock" : "unlock"
    : domain === "cover"
      ? desiredActive ? "open_cover" : "close_cover"
      : domain === "button"
        ? "press"
        : desiredActive ? "turn_on" : "turn_off";
  const commandId = crypto.randomUUID();
  await getDb().insert(agentCommands).values({
    publicId: commandId,
    dossierId: selected.dossier.id,
    action: "ha.services.call",
    payloadJson: JSON.stringify({
      domain,
      service,
      data: { entity_id: resolved.item.entityId },
    }),
  });
  return { accepted: true, commandId };
}

async function automationTarget(
  publicDeviceId: string,
  dossierPublicId?: string | null,
) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const allowShowroomEntities =
    selected.dossier.reference.toUpperCase().includes("SHOWROOM");
  const resolved = controlBindings
    .filter((binding) => binding.controllable !== false)
    .map((binding) => ({
      binding,
      item: resolvedControl(inventory, binding, allowShowroomEntities),
    }))
    .find(({ item }) =>
      item && publicId(item.entityId) === publicDeviceId
    );
  if (!resolved?.item) throw new Error("DEVICE_NOT_FOUND");
  return { selected, item: resolved.item };
}

async function automationEntity(
  publicAutomationId: string,
  dossierPublicId?: string | null,
) {
  const selected = await selectAgentForDossier(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const item = inventory.find((candidate) =>
    candidate.domain === "automation" &&
    candidate.name.startsWith("1.2.3 Home") &&
    publicId(candidate.entityId, "regle") === publicAutomationId
  );
  if (!item) throw new Error("AUTOMATION_NOT_FOUND");
  return { selected, item };
}

function automationService(domain: string, desiredActive: boolean) {
  if (domain === "lock") return desiredActive ? "lock" : "unlock";
  if (domain === "cover") return desiredActive ? "open_cover" : "close_cover";
  return desiredActive ? "turn_on" : "turn_off";
}

export async function queueAgentAutomationCreate(
  input: {
    name: string;
    time: string;
    publicDeviceId: string;
    desiredActive: boolean;
  },
  dossierPublicId?: string | null,
) {
  const name = input.name.trim();
  if (name.length < 3 || name.length > 80) throw new Error("INVALID_NAME");
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(input.time)) {
    throw new Error("INVALID_TIME");
  }
  const { selected, item } = await automationTarget(
    input.publicDeviceId,
    dossierPublicId,
  );
  const domain = item.entityId.split(".")[0];
  const commandId = crypto.randomUUID();
  await getDb().insert(agentCommands).values({
    publicId: commandId,
    dossierId: selected.dossier.id,
    action: "ha.automation.create",
    payloadJson: JSON.stringify({
      name,
      time: input.time,
      entityId: item.entityId,
      domain,
      service: automationService(domain, input.desiredActive),
    }),
  });
  return { accepted: true, commandId };
}

export async function queueAgentAutomationState(
  publicAutomationId: string,
  enabled: boolean,
  dossierPublicId?: string | null,
) {
  const { selected, item } = await automationEntity(
    publicAutomationId,
    dossierPublicId,
  );
  const commandId = crypto.randomUUID();
  await getDb().insert(agentCommands).values({
    publicId: commandId,
    dossierId: selected.dossier.id,
    action: "ha.services.call",
    payloadJson: JSON.stringify({
      domain: "automation",
      service: enabled ? "turn_on" : "turn_off",
      data: { entity_id: item.entityId },
    }),
  });
  return { accepted: true, commandId };
}

export async function queueAgentAutomationDelete(
  publicAutomationId: string,
  dossierPublicId?: string | null,
) {
  const { selected, item } = await automationEntity(
    publicAutomationId,
    dossierPublicId,
  );
  const commandId = crypto.randomUUID();
  await getDb().insert(agentCommands).values({
    publicId: commandId,
    dossierId: selected.dossier.id,
    action: "ha.automation.delete",
    payloadJson: JSON.stringify({ entityId: item.entityId }),
  });
  return { accepted: true, commandId };
}
