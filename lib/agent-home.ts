import { desc, eq } from "drizzle-orm";
import { getDb } from "../db";
import { agentBoxes, agentCommands, installationDossiers } from "../db/schema";
import { relayHouseIdForDossier } from "./relay-house";

type InventoryItem = {
  entityId: string;
  name: string;
  domain: string;
  state: string;
  deviceClass?: string | null;
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
    entityIds: ["climate.152832117468341_climate_zone1", "input_boolean.demo_heating"],
    label: "Chauffage", icon: "♨", room: "Maison", category: "Confort",
  },
  {
    entityIds: ["switch.filtration_piscine_switch", "input_boolean.demo_pool_filtration"],
    label: "Filtration", icon: "≋", room: "Piscine", category: "Piscine",
  },
  {
    entityIds: ["climate.pompe_a_chaleur_piscine", "input_boolean.demo_pool_heat_pump"],
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
    entityIds: [
      "switch.ce_wifi_commutateur_sur_rail_din_avec_mesure_2_switch",
      "input_boolean.chauffe_eau_shelly",
    ],
    label: "Ballon d’eau chaude", icon: "♨", room: "Local technique", category: "Eau chaude",
  },
];

const valueBindings = {
  solar: [
    "sensor.inverter_pv_power",
    "sensor.onduleur_pv_power",
    "input_number.demo_solar_power",
  ],
  home: [
    "sensor.shellyem3_483fdac38616_channel_b_power",
    "sensor.inverter_load_power",
    "sensor.onduleur_load_power",
    "input_number.demo_house_power",
  ],
  grid: [
    "sensor.shellyem3_483fdac38616_channel_c_power",
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
    "sensor.1_2_3_home_today_consumption",
    "sensor.inverter_today_load_consumption",
    "sensor.onduleur_today_load_consumption",
  ],
  filtration: ["sensor.filtration_piscine_puissance"],
  hotWaterPower: [
    "sensor.ce_wifi_commutateur_sur_rail_din_avec_mesure_2_puissance",
    "sensor.1_2_3_home_puissance_chauffe_eau",
  ],
  hotWaterAvailable: ["sensor.1_2_3_home_eau_chaude_disponible"],
  hotWaterTemperature: ["input_number.chauffe_eau_temperature"],
  hotWaterMode: ["input_select.chauffe_eau_mode"],
  indoorTemperature: ["input_number.demo_indoor_temperature"],
  heatingSetpoint: ["input_number.demo_heating_setpoint"],
  poolTemperature: ["input_number.demo_pool_temperature"],
  poolSetpoint: ["input_number.demo_pool_setpoint"],
  teslaBattery: [
    "sensor.tesla_model_x_battery",
    "sensor.tesla_y_battery",
    "input_number.demo_tesla_soc",
  ],
  teslaPower: [
    "sensor.tesla_model_x_charger_power",
    "sensor.tesla_y_charger_power",
    "input_number.demo_tesla_charge_power",
  ],
  teslaPlugged: [
    "binary_sensor.tesla_model_x_charger",
    "binary_sensor.tesla_model_x_charger_connected",
    "sensor.tesla_model_x_charging_state",
    "binary_sensor.tesla_y_charger",
    "binary_sensor.tesla_y_charger_connected",
    "sensor.tesla_y_charging_state",
  ],
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

function find(inventory: InventoryItem[], ids: readonly string[]) {
  const matches = ids
    .map((id) => inventory.find((item) => item.entityId === id))
    .filter((item): item is InventoryItem => Boolean(item));
  return matches.find((item) => !["unknown", "unavailable"].includes(item.state))
    ?? matches[0]
    ?? null;
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
  const online = Boolean(
    selected.agent.lastSeenAt &&
    Date.now() - Date.parse(selected.agent.lastSeenAt) < 120_000
  );
  const ringOnline = Boolean(
    ringSource?.agent.lastSeenAt &&
    Date.now() - Date.parse(ringSource.agent.lastSeenAt) < 120_000
  );

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

  const devices = controlBindings
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
        solar: formatted(scopedFind(inventory, valueBindings.solar, allowShowroomEntities), "W", "0 W"),
        home: formatted(scopedFind(inventory, valueBindings.home, allowShowroomEntities), "W", "0 W"),
        grid: formatted(scopedFind(inventory, valueBindings.grid, allowShowroomEntities), "W", "0 W"),
        battery: formatted(scopedFind(inventory, valueBindings.battery, allowShowroomEntities), "%", "0 %"),
        batteryPower: formatted(scopedFind(inventory, valueBindings.batteryPower, allowShowroomEntities), "W", "0 W"),
        filtration: formatted(scopedFind(inventory, valueBindings.filtration, allowShowroomEntities), "W", "0 W"),
        dailyProduction: formatted(scopedFind(inventory, valueBindings.dailyProduction, allowShowroomEntities), "kWh"),
        dailyConsumption: formatted(scopedFind(inventory, valueBindings.dailyConsumption, allowShowroomEntities), "kWh"),
      },
      controls,
      security: ringSecurity,
      comfort: {
        indoorTemperature: formatted(scopedFind(inventory, valueBindings.indoorTemperature, allowShowroomEntities), "°C"),
        heatingSetpoint: formatted(scopedFind(inventory, valueBindings.heatingSetpoint, allowShowroomEntities), "°C"),
        poolTemperature: formatted(scopedFind(inventory, valueBindings.poolTemperature, allowShowroomEntities), "°C"),
        poolSetpoint: formatted(scopedFind(inventory, valueBindings.poolSetpoint, allowShowroomEntities), "°C"),
        hotWaterTemperature: formatted(scopedFind(inventory, valueBindings.hotWaterTemperature, allowShowroomEntities), "°C"),
        hotWaterAvailable: formatted(scopedFind(inventory, valueBindings.hotWaterAvailable, allowShowroomEntities), "%"),
        hotWaterPower: formatted(scopedFind(inventory, valueBindings.hotWaterPower, allowShowroomEntities), "W", "0 W"),
        hotWaterMode: formatted(scopedFind(inventory, valueBindings.hotWaterMode, allowShowroomEntities), ""),
        teslaBattery: formatted(scopedFind(inventory, valueBindings.teslaBattery, allowShowroomEntities), "%"),
        teslaPower: formatted(scopedFind(inventory, valueBindings.teslaPower, allowShowroomEntities), "W", "0 W"),
        teslaPlugged: formatted(scopedFind(inventory, valueBindings.teslaPlugged, allowShowroomEntities), "", "off"),
        demoMode: formatted(scopedFind(inventory, valueBindings.demoMode, allowShowroomEntities), ""),
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
