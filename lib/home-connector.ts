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
  category: string;
  state: string;
  available: boolean;
  battery: number | null;
  lastChanged: string;
};

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
  solar: ["sensor.onduleur_pv_power", "puissance solaire", "production solaire", "solar power", "pv power"],
  home: ["sensor.shellyem3_483fdac38616_channel_b_power", "consommation maison", "puissance maison", "home power"],
  grid: ["sensor.shellyem3_483fdac38616_channel_c_power", "puissance reseau", "grid power"],
  battery: ["sensor.batterie_deye_soc", "sensor.onduleur_battery", "niveau batterie", "batterie soc"],
  batteryPower: ["sensor.onduleur_battery_power", "puissance batterie", "battery power"],
  filtrationPower: ["sensor.filtration_piscine_puissance", "puissance filtration"],
  dailyProduction: ["sensor.onduleur_today_production", "production journaliere"],
  dailyConsumption: ["sensor.onduleur_today_load_consumption", "consommation journaliere"],
  gate: ["switch.shellyplus1_78ee4cc38b48", "portail"],
  terrace: ["light.terrasse", "terrasse"],
  poolHeat: ["climate.pompe_a_chaleur_piscine", "pac piscine"],
  filtration: ["switch.filtration_piscine_switch", "filtration piscine"],
  spa: ["switch.mspa_oslo_f_os063wp_heater", "spa heater"],
  spaFiltration: ["switch.mspa_oslo_f_os063wp_filter", "filtration spa"],
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

async function haFetch<T>(path: string): Promise<T> {
  const { baseUrl, token } = config();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`CONNECTOR_HTTP_${response.status}`);
    return await response.json() as T;
  } finally {
    clearTimeout(timeout);
  }
}

function publicId(entityId: string) {
  let hash = 2166136261;
  for (const char of entityId) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `appareil_${(hash >>> 0).toString(36)}`;
}

function text(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export async function getPortalHome() {
  const [api, states] = await Promise.all([
    haFetch<{ message: string }>("/api/"),
    haFetch<HaState[]>("/api/states"),
  ]);

  const devices = states
    .filter(({ entity_id, attributes }) => {
      const domain = entity_id.split(".")[0];
      const name = text(attributes?.friendly_name, "");
      return clientDomains.has(domain) && !hiddenNamePatterns.some((pattern) => pattern.test(name));
    })
    .slice(0, 200)
    .map((entity): PortalDevice => {
      const domain = entity.entity_id.split(".")[0];
      const attributes = entity.attributes ?? {};
      const battery =
        typeof attributes.battery_level === "number" ? attributes.battery_level :
        typeof attributes.battery === "number" ? attributes.battery : null;

      return {
        publicId: publicId(entity.entity_id),
        name: text(attributes.friendly_name, "Appareil"),
        room: text(attributes.area_name, "Maison"),
        category: categoryLabels[domain] ?? "Autre",
        state: entity.state === "unavailable" ? "Indisponible" : entity.state,
        available: entity.state !== "unavailable" && entity.state !== "unknown",
        battery,
        lastChanged: entity.last_changed,
      };
    });

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
