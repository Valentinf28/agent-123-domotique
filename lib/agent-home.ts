import { desc, eq } from "drizzle-orm";
import { getDb } from "../db";
import { agentBoxes, agentCommands, installationDossiers } from "../db/schema";

type InventoryItem = {
  entityId: string;
  name: string;
  domain: string;
  state: string;
  deviceClass?: string | null;
};

type ControlBinding = {
  entityId: string;
  label: string;
  icon: string;
  room: string;
  category: string;
};

const controlBindings: ControlBinding[] = [
  { entityId: "input_boolean.demo_heating", label: "Chauffage", icon: "♨", room: "Maison", category: "Confort" },
  { entityId: "input_boolean.demo_pool_filtration", label: "Filtration", icon: "≋", room: "Piscine", category: "Piscine" },
  { entityId: "input_boolean.demo_pool_heat_pump", label: "PAC piscine", icon: "♨", room: "Piscine", category: "Piscine" },
  { entityId: "input_boolean.demo_nuki_locked", label: "Serrure Nuki", icon: "▣", room: "Entrée", category: "Sécurité" },
  { entityId: "input_boolean.demo_camera_surveillance", label: "Caméras", icon: "◉", room: "Extérieur", category: "Sécurité" },
  { entityId: "input_boolean.chauffe_eau_shelly", label: "Ballon d’eau chaude", icon: "♨", room: "Local technique", category: "Eau chaude" },
];

const valueBindings = {
  solar: [
    "sensor.inverter_pv_power",
    "sensor.onduleur_pv_power",
    "input_number.demo_solar_power",
  ],
  home: [
    "sensor.inverter_load_power",
    "sensor.onduleur_load_power",
    "input_number.demo_house_power",
  ],
  grid: [
    "sensor.inverter_grid_power",
    "sensor.onduleur_grid_power",
    "sensor.1_2_3_home_puissance_reseau",
  ],
  battery: [
    "sensor.inverter_battery",
    "sensor.onduleur_battery",
    "input_number.demo_battery_soc",
  ],
  batteryPower: [
    "sensor.inverter_battery_power",
    "sensor.onduleur_battery_power",
    "sensor.1_2_3_home_puissance_batterie",
  ],
  dailyProduction: [
    "sensor.inverter_today_production",
    "sensor.onduleur_today_production",
  ],
  dailyConsumption: [
    "sensor.inverter_today_load_consumption",
    "sensor.onduleur_today_load_consumption",
  ],
  filtration: ["sensor.filtration_piscine_puissance"],
  hotWaterPower: ["sensor.1_2_3_home_puissance_chauffe_eau"],
  hotWaterAvailable: ["sensor.1_2_3_home_eau_chaude_disponible"],
  hotWaterTemperature: ["input_number.chauffe_eau_temperature"],
  hotWaterMode: ["input_select.chauffe_eau_mode"],
  indoorTemperature: ["input_number.demo_indoor_temperature"],
  heatingSetpoint: ["input_number.demo_heating_setpoint"],
  poolTemperature: ["input_number.demo_pool_temperature"],
  poolSetpoint: ["input_number.demo_pool_setpoint"],
  teslaBattery: ["input_number.demo_tesla_soc"],
  teslaPower: ["input_number.demo_tesla_charge_power"],
  demoMode: ["input_select.demo_mode"],
} as const;

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

function find(inventory: InventoryItem[], ids: readonly string[]) {
  return ids.map((id) => inventory.find((item) => item.entityId === id)).find(Boolean) ?? null;
}

function formatted(item: InventoryItem | null, unit: string, fallback = "—") {
  if (!item || ["unknown", "unavailable"].includes(item.state)) return fallback;
  const numeric = Number(item.state);
  if (!Number.isFinite(numeric)) return item.state;
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(numeric)}${unit ? ` ${unit}` : ""}`;
}

function active(item: InventoryItem | null) {
  return Boolean(item && ["on", "open", "heat", "heating", "locked"].includes(item.state.toLowerCase()));
}

async function selectedAgent(dossierPublicId?: string | null) {
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
      inventory.some((item) => item.entityId === binding.entityId)
    );
  }) ?? agents[0];
  if (!agent) return null;
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.id, agent.dossierId)).limit(1);
  return dossier ? { agent, dossier } : null;
}

export async function getAgentPortalHome(dossierPublicId?: string | null) {
  const selected = await selectedAgent(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const inventory = parseInventory(selected.agent.inventoryJson);
  const byEntity = new Map(inventory.map((item) => [item.entityId, item]));
  const online = Boolean(
    selected.agent.lastSeenAt &&
    Date.now() - Date.parse(selected.agent.lastSeenAt) < 120_000
  );

  const controls = controlBindings.map((binding) => {
    const item = byEntity.get(binding.entityId) ?? null;
    return {
      publicId: publicId(binding.entityId, "commande"),
      label: binding.label,
      icon: binding.icon,
      active: active(item),
      available: online && Boolean(item) && !["unknown", "unavailable"].includes(item.state),
    };
  });

  const devices = controlBindings.map((binding) => {
    const item = byEntity.get(binding.entityId) ?? null;
    const available = online && Boolean(item) && !["unknown", "unavailable"].includes(item.state);
    return {
      publicId: publicId(binding.entityId),
      name: binding.label,
      room: binding.room,
      areaPublicId: publicId(binding.room, "piece"),
      category: binding.category,
      state: available ? active(item) ? "on" : "off" : "unavailable",
      available,
      battery: null,
      visible: true,
      lastChanged: selected.agent.lastSeenAt ?? new Date(0).toISOString(),
    };
  });

  const tesla = find(inventory, valueBindings.teslaBattery);
  if (tesla) {
    devices.push({
      publicId: publicId(tesla.entityId),
      name: "Tesla",
      room: "Garage",
      areaPublicId: publicId("Garage", "piece"),
      category: "Véhicule",
      state: tesla.state,
      available: online,
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

  return {
    connected: online,
    source: "agent",
    dossier: {
      publicId: selected.dossier.publicId,
      reference: selected.dossier.reference,
      name: selected.dossier.customerName,
    },
    deviceCount: devices.length,
    unavailableCount: devices.filter((device) => !device.available).length,
    lowBatteryCount: devices.filter((device) => device.battery !== null && device.battery < 20).length,
    devices,
    areas: ["Maison", "Entrée", "Piscine", "Extérieur", "Garage", "Local technique"]
      .map((name) => ({ publicId: publicId(name, "piece"), name })),
    automations,
    mobileOverview: {
      energy: {
        solar: formatted(find(inventory, valueBindings.solar), "W", "0 W"),
        home: formatted(find(inventory, valueBindings.home), "W", "0 W"),
        grid: formatted(find(inventory, valueBindings.grid), "W", "0 W"),
        battery: formatted(find(inventory, valueBindings.battery), "%", "0 %"),
        batteryPower: formatted(find(inventory, valueBindings.batteryPower), "W", "0 W"),
        filtration: formatted(find(inventory, valueBindings.filtration), "W", "0 W"),
        dailyProduction: formatted(find(inventory, valueBindings.dailyProduction), "kWh"),
        dailyConsumption: formatted(find(inventory, valueBindings.dailyConsumption), "kWh"),
      },
      controls,
      comfort: {
        indoorTemperature: formatted(find(inventory, valueBindings.indoorTemperature), "°C"),
        heatingSetpoint: formatted(find(inventory, valueBindings.heatingSetpoint), "°C"),
        poolTemperature: formatted(find(inventory, valueBindings.poolTemperature), "°C"),
        poolSetpoint: formatted(find(inventory, valueBindings.poolSetpoint), "°C"),
        hotWaterTemperature: formatted(find(inventory, valueBindings.hotWaterTemperature), "°C"),
        hotWaterAvailable: formatted(find(inventory, valueBindings.hotWaterAvailable), "%"),
        hotWaterPower: formatted(find(inventory, valueBindings.hotWaterPower), "W", "0 W"),
        hotWaterMode: formatted(find(inventory, valueBindings.hotWaterMode), ""),
        teslaBattery: formatted(find(inventory, valueBindings.teslaBattery), "%"),
        teslaPower: formatted(find(inventory, valueBindings.teslaPower), "W", "0 W"),
        demoMode: formatted(find(inventory, valueBindings.demoMode), ""),
      },
    },
  };
}

export async function queueAgentControl(
  publicControlId: string,
  desiredActive: boolean,
  dossierPublicId?: string | null,
) {
  const selected = await selectedAgent(dossierPublicId);
  if (!selected) throw new Error("CONNECTOR_NOT_CONFIGURED");
  const binding = controlBindings.find(
    (candidate) => publicId(candidate.entityId, "commande") === publicControlId,
  );
  if (!binding) throw new Error("CONTROL_NOT_FOUND");
  const commandId = crypto.randomUUID();
  await getDb().insert(agentCommands).values({
    publicId: commandId,
    dossierId: selected.dossier.id,
    action: "ha.services.call",
    payloadJson: JSON.stringify({
      domain: "input_boolean",
      service: desiredActive ? "turn_on" : "turn_off",
      data: { entity_id: binding.entityId },
    }),
  });
  return { accepted: true, commandId };
}
