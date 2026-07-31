import { ENERGY_PROFILE } from "./energy-profile.generated";
import { HOUSE_BINDINGS } from "./house-bindings.generated";

type HaState = {
  entity_id: string;
  state: string;
  attributes?: Record<string, unknown>;
  last_changed: string;
};

export type PortalDevice = {
  publicId: string;
  name: string;
  room: string;
  areaPublicId: string | null;
  category: string;
  state: string;
  available: boolean;
  battery: number | null;
  visible: boolean;
  lastChanged: string;
};

export type PortalArea = {
  publicId: string;
  name: string;
};

export type PortalAutomation = {
  publicId: string;
  name: string;
  enabled: boolean;
  lastTriggered: string | null;
  trigger: string;
  action: string;
};

type HaEntityRegistryEntry = {
  entity_id: string;
  name?: string | null;
  original_name?: string | null;
  area_id?: string | null;
  device_id?: string | null;
  labels?: string[];
  entity_category?: "config" | "diagnostic" | null;
  hidden_by?: string | null;
  disabled_by?: string | null;
};

type HaDeviceRegistryEntry = {
  id: string;
  name?: string | null;
  name_by_user?: string | null;
  model?: string | null;
  manufacturer?: string | null;
  area_id?: string | null;
  labels?: string[];
  disabled_by?: string | null;
};

type HaAreaRegistryEntry = {
  area_id: string;
  name: string;
};

type HaLabelRegistryEntry = {
  label_id: string;
  name: string;
};

const MOBILE_HIDDEN_LABEL_NAME = "Masqué application Ma Maison";

const categoryLabels: Record<string, string> = {
  light: "Éclairage",
  switch: "Interrupteurs",
  climate: "Climat",
  cover: "Volets",
  lock: "Sécurité",
  binary_sensor: "Capteurs",
  sensor: "Capteurs",
  fan: "Ventilation",
  vacuum: "Entretien",
  media_player: "Multimédia",
};

const hiddenNamePatterns = [
  /^backup\b/i,
  /^remote ui$/i,
  /^sun\b/i,
  /\b(update|mise à jour|uptime|version|diagnostic|dernière sauvegarde)\b/i,
];

const clientDomains = new Set([
  "light", "switch", "climate", "cover", "lock", "binary_sensor",
  "fan", "vacuum", "media_player",
]);

const overviewBindings: Record<string, string[]> = {
  solar: [...ENERGY_PROFILE.solarPower],
  home: [...ENERGY_PROFILE.homePower],
  grid: [...ENERGY_PROFILE.gridPower],
  battery: [...ENERGY_PROFILE.batteryLevel],
  batteryPower: [...ENERGY_PROFILE.batteryPower],
  filtrationPower: [...HOUSE_BINDINGS.filtrationPower],
  dailyProduction: [...ENERGY_PROFILE.dailyProduction],
  dailyConsumption: [...ENERGY_PROFILE.dailyConsumption],
  dailyImport: [...ENERGY_PROFILE.dailyImport],
  dailyExport: [...ENERGY_PROFILE.dailyExport],
  monthlyProduction: [...ENERGY_PROFILE.monthlyProduction],
  monthlyConsumption: [...ENERGY_PROFILE.monthlyConsumption],
  monthlyImport: [...ENERGY_PROFILE.monthlyImport],
  monthlyExport: [...ENERGY_PROFILE.monthlyExport],
  yearlyProduction: [...ENERGY_PROFILE.yearlyProduction],
  yearlyConsumption: [...ENERGY_PROFILE.yearlyConsumption],
  yearlyImport: [...ENERGY_PROFILE.yearlyImport],
  yearlyExport: [...ENERGY_PROFILE.yearlyExport],
  gate: [...HOUSE_BINDINGS.gate],
  terrace: [...HOUSE_BINDINGS.terrace],
  poolHeat: [...HOUSE_BINDINGS.poolHeatPump],
  filtration: [...HOUSE_BINDINGS.filtration],
  spa: [...HOUSE_BINDINGS.spa],
  spaFiltration: [...HOUSE_BINDINGS.spaFiltration],
};

function normalize(value = "") {
  return value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim();
}

function resolve(states: HaState[], aliases: string[]) {
  return states.map((entity) => {
    const source = normalize(`${entity.entity_id} ${text(entity.attributes?.friendly_name, "")}`);
    const id = normalize(entity.entity_id);
    const score = aliases.reduce((best, alias) => {
      const target = normalize(alias);
      if (id === target) return Math.max(best, 1000);
      if (source.includes(target)) return Math.max(best, 100 + target.length);
      return best;
    }, 0);
    return { entity, score };
  }).sort((a, b) => b.score - a.score)[0]?.score
    ? states.map((entity) => {
        const source = normalize(`${entity.entity_id} ${text(entity.attributes?.friendly_name, "")}`);
        const id = normalize(entity.entity_id);
        const score = aliases.reduce((best, alias) => {
          const target = normalize(alias);
          return Math.max(best, id === target ? 1000 : source.includes(target) ? 100 + target.length : 0);
        }, 0);
        return { entity, score };
      }).sort((a, b) => b.score - a.score)[0].entity
    : null;
}

function displayValue(entity: HaState | null, fallback: string) {
  if (!entity || ["unknown", "unavailable"].includes(entity.state)) return fallback;
  const numeric = Number(entity.state);
  const value = Number.isFinite(numeric)
    ? new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(numeric)
    : entity.state;
  const unit = text(entity.attributes?.unit_of_measurement, "");
  return `${value}${unit ? ` ${unit}` : ""}`;
}

function config() {
  const baseUrl = process.env.HA_BASE_URL?.trim().replace(/\/+$/, "");
  const token = process.env.HA_ACCESS_TOKEN?.trim();
  if (!baseUrl || !token) throw new Error("CONNECTOR_NOT_CONFIGURED");
  return { baseUrl, token };
}

async function haFetch<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { baseUrl, token } = config();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: init.method ?? "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`CONNECTOR_HTTP_${response.status}`);
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } finally {
    clearTimeout(timeout);
  }
}

function publicId(entityId: string, prefix = "appareil") {
  let hash = 2166136261;
  for (const char of entityId) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${prefix}_${(hash >>> 0).toString(36)}`;
}

function text(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

async function haWebSocketCommand<T>(
  type: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const { baseUrl, token } = config();
  const response = await fetch(`${baseUrl}/api/websocket`, {
    headers: { Upgrade: "websocket" },
  });
  const socket = response.webSocket;
  if (!socket) throw new Error("CONNECTOR_WEBSOCKET");
  socket.accept();

  return await new Promise<T>((resolve, reject) => {
    const timeout = setTimeout(() => {
      socket.close(1011, "Délai dépassé");
      reject(new Error("CONNECTOR_TIMEOUT"));
    }, 8000);
    const finish = (callback: () => void) => {
      clearTimeout(timeout);
      callback();
      socket.close(1000, "Terminé");
    };

    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(String(event.data)) as {
          id?: number;
          type?: string;
          success?: boolean;
          result?: T;
        };
        if (message.type === "auth_required") {
          socket.send(JSON.stringify({ type: "auth", access_token: token }));
          return;
        }
        if (message.type === "auth_invalid") {
          finish(() => reject(new Error("CONNECTOR_AUTH")));
          return;
        }
        if (message.type === "auth_ok") {
          socket.send(JSON.stringify({ id: 1, type, ...payload }));
          return;
        }
        if (message.id === 1 && message.type === "result") {
          if (message.success) finish(() => resolve(message.result as T));
          else finish(() => reject(new Error("CONNECTOR_COMMAND")));
        }
      } catch {
        finish(() => reject(new Error("CONNECTOR_MESSAGE")));
      }
    });
    socket.addEventListener("error", () =>
      finish(() => reject(new Error("CONNECTOR_WEBSOCKET")))
    );
  });
}

async function registries() {
  const [entities, devices, areas, labels] = await Promise.all([
    haWebSocketCommand<HaEntityRegistryEntry[]>("config/entity_registry/list"),
    haWebSocketCommand<HaDeviceRegistryEntry[]>("config/device_registry/list"),
    haWebSocketCommand<HaAreaRegistryEntry[]>("config/area_registry/list"),
    haWebSocketCommand<HaLabelRegistryEntry[]>("config/label_registry/list")
      .catch(() => []),
  ]);
  return { entities, devices, areas, labels };
}

export async function getPortalHome() {
  const [api, states, registry] = await Promise.all([
    haFetch<{ message: string }>("/api/"),
    haFetch<HaState[]>("/api/states"),
    registries(),
  ]);
  const areaRegistry = new Map(
    registry.areas.map((entry) => [entry.area_id, entry]),
  );
  const mobileHiddenLabel = registry.labels.find(
    (label) => label.name === MOBILE_HIDDEN_LABEL_NAME,
  );

  const stateRegistry = new Map(states.map((state) => [state.entity_id, state]));
  const domainPriority = [
    "light", "switch", "climate", "cover", "lock", "vacuum",
    "fan", "media_player", "binary_sensor",
  ];
  const devices = registry.devices
    .filter((device) => !device.disabled_by)
    .map((device): PortalDevice | null => {
      const entries = registry.entities.filter((entry) =>
        entry.device_id === device.id &&
        clientDomains.has(entry.entity_id.split(".")[0]) &&
        !entry.entity_category &&
        !entry.hidden_by &&
        !entry.disabled_by
      );
      if (!entries.length) return null;
      const primaryEntry = [...entries].sort((a, b) =>
        domainPriority.indexOf(a.entity_id.split(".")[0]) -
        domainPriority.indexOf(b.entity_id.split(".")[0])
      )[0];
      const primaryState = stateRegistry.get(primaryEntry.entity_id);
      const displayName = text(
        device.name_by_user,
        text(device.name, text(device.model, text(
          primaryState?.attributes?.friendly_name,
          "Appareil",
        ))),
      );
      if (hiddenNamePatterns.some((pattern) => pattern.test(displayName))) {
        return null;
      }
      const areaId = device.area_id ?? primaryEntry.area_id ?? null;
      const batteryState = registry.entities
        .filter((entry) => entry.device_id === device.id)
        .map((entry) => stateRegistry.get(entry.entity_id))
        .find((state) =>
          state?.attributes?.device_class === "battery" &&
          Number.isFinite(Number(state.state))
        );
      const battery = batteryState ? Number(batteryState.state) : null;
      const available = Boolean(
        primaryState &&
        !["unavailable", "unknown"].includes(primaryState.state)
      );
      return {
        publicId: publicId(device.id),
        name: displayName,
        room: areaId ? text(areaRegistry.get(areaId)?.name, "Maison") : "Maison",
        areaPublicId: areaId ? publicId(areaId, "piece") : null,
        category: categoryLabels[primaryEntry.entity_id.split(".")[0]] ?? "Autre",
        state: available ? primaryState?.state ?? "Prêt" : "Indisponible",
        available,
        battery,
        visible: mobileHiddenLabel
          ? !(device.labels ?? []).includes(mobileHiddenLabel.label_id)
          : true,
        lastChanged: primaryState?.last_changed ?? new Date(0).toISOString(),
      };
    })
    .filter((device): device is PortalDevice => device !== null)
    .sort((a, b) => a.name.localeCompare(b.name, "fr"));

  const automations = states
    .filter(({ entity_id }) => entity_id.startsWith("automation."))
    .map((entity): PortalAutomation => ({
      publicId: publicId(entity.entity_id, "regle"),
      name: text(entity.attributes?.friendly_name, "Automatisation"),
      enabled: entity.state === "on",
      lastTriggered: typeof entity.attributes?.last_triggered === "string"
        ? entity.attributes.last_triggered
        : null,
      trigger: "Déclencheur configuré",
      action: "Actions configurées",
    }));

  const value = (key: string, fallback: string) =>
    displayValue(resolve(states, overviewBindings[key]), fallback);
  const control = (key: string, label: string) => {
    const entity = resolve(states, overviewBindings[key]);
    const state = entity?.state.toLowerCase() ?? "unavailable";
    return {
      label,
      active: ["on", "open", "heat", "heating", "unlocked"].includes(state),
      available: !["unavailable", "unknown"].includes(state),
    };
  };

  return {
    connected: api.message === "API running.",
    deviceCount: devices.length,
    unavailableCount: devices.filter((device) => !device.available).length,
    lowBatteryCount: devices.filter((device) => device.battery !== null && device.battery < 20).length,
    devices,
    areas: registry.areas
      .map((area): PortalArea => ({
        publicId: publicId(area.area_id, "piece"),
        name: area.name,
      }))
      .sort((a, b) => a.name.localeCompare(b.name, "fr")),
    automations,
    mobileOverview: {
      energy: {
        solar: value("solar", "0 W"),
        home: value("home", "0 W"),
        grid: value("grid", "0 W"),
        battery: value("battery", "0 %"),
        batteryPower: value("batteryPower", "0 W"),
        filtration: value("filtrationPower", "0 W"),
        dailyProduction: value("dailyProduction", "—"),
        dailyConsumption: value("dailyConsumption", "—"),
        dailyImport: value("dailyImport", "—"),
        dailyExport: value("dailyExport", "—"),
        monthlyProduction: value("monthlyProduction", "—"),
        monthlyConsumption: value("monthlyConsumption", "—"),
        monthlyImport: value("monthlyImport", "—"),
        monthlyExport: value("monthlyExport", "—"),
        yearlyProduction: value("yearlyProduction", "—"),
        yearlyConsumption: value("yearlyConsumption", "—"),
        yearlyImport: value("yearlyImport", "—"),
        yearlyExport: value("yearlyExport", "—"),
      },
      controls: [
        control("gate", "Portail"),
        control("terrace", "Terrasse"),
        control("poolHeat", "PAC piscine"),
        control("filtration", "Filtration"),
        control("spa", "Spa"),
        control("spaFiltration", "Filtration spa"),
      ],
    },
  };
}

async function resolveDevice(publicDeviceId: string) {
  const registry = await registries();
  const device = registry.devices.find(
    (entry) => publicId(entry.id) === publicDeviceId,
  );
  if (!device) throw new Error("DEVICE_NOT_FOUND");
  return { device, registry };
}

export async function updatePortalDevice(
  publicDeviceId: string,
  input: {
    name?: string;
    areaPublicId?: string | null;
    visible?: boolean;
  },
) {
  const { device, registry } = await resolveDevice(publicDeviceId);
  const update: Record<string, unknown> = { device_id: device.id };

  if (input.name !== undefined) {
    const name = input.name.trim();
    if (name.length < 2 || name.length > 80) throw new Error("INVALID_NAME");
    update.name_by_user = name;
  }
  if (input.areaPublicId !== undefined) {
    if (input.areaPublicId === null) update.area_id = null;
    else {
      const area = registry.areas.find((entry) =>
        publicId(entry.area_id, "piece") === input.areaPublicId
      );
      if (!area) throw new Error("AREA_NOT_FOUND");
      update.area_id = area.area_id;
    }
  }
  if (input.visible !== undefined) {
    let mobileHiddenLabel = registry.labels.find(
      (label) => label.name === MOBILE_HIDDEN_LABEL_NAME,
    );
    if (!mobileHiddenLabel && !input.visible) {
      mobileHiddenLabel = await haWebSocketCommand<HaLabelRegistryEntry>(
        "config/label_registry/create",
        { name: MOBILE_HIDDEN_LABEL_NAME },
      );
    }
    if (mobileHiddenLabel) {
      const labels = new Set(device.labels ?? []);
      if (input.visible) labels.delete(mobileHiddenLabel.label_id);
      else labels.add(mobileHiddenLabel.label_id);
      update.labels = [...labels];
    }
  }

  await haWebSocketCommand("config/device_registry/update", update);
  return { updated: true };
}

async function resolveAutomation(publicAutomationId: string) {
  const states = await haFetch<HaState[]>("/api/states");
  const state = states.find((entry) =>
    entry.entity_id.startsWith("automation.") &&
    publicId(entry.entity_id, "regle") === publicAutomationId
  );
  if (!state) throw new Error("AUTOMATION_NOT_FOUND");
  return state;
}

export async function setPortalAutomationEnabled(
  publicAutomationId: string,
  enabled: boolean,
) {
  const automation = await resolveAutomation(publicAutomationId);
  await haFetch(`/api/services/automation/${enabled ? "turn_on" : "turn_off"}`, {
    method: "POST",
    body: { entity_id: automation.entity_id },
  });
  return { updated: true };
}

export async function deletePortalAutomation(publicAutomationId: string) {
  const automation = await resolveAutomation(publicAutomationId);
  const automationId = automation.attributes?.id;
  if (typeof automationId !== "string" || !automationId) {
    throw new Error("AUTOMATION_NOT_MANAGED");
  }
  await haFetch(
    `/api/config/automation/config/${encodeURIComponent(automationId)}`,
    { method: "DELETE" },
  );
  return { deleted: true };
}
