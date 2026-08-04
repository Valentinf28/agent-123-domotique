export type ErpDossierSummary = {
  id: number;
  reference: string;
  title: string;
  customerName: string;
  city?: string | null;
  postalCode?: string | null;
  status?: string | null;
  solarPeakKwc?: string | number | null;
  hasBattery?: boolean;
};

export type ErpDevice = {
  category?: string | null;
  quantity?: number | null;
  brand?: string | null;
  model?: string | null;
  comments?: string | null;
};

export type ErpDossierDetail = ErpDossierSummary & {
  address?: string | null;
  panelCount?: string | number | null;
  panelModel?: string | null;
  inverterModel?: string | null;
  battery?: string | null;
  orientation?: string | null;
  inclination?: string | null;
  devices?: ErpDevice[];
  devicesSource?: string | null;
  domotiqueConfirmed?: boolean;
};

export type SolarArrayConfiguration = {
  id: string;
  label: string;
  peakWatts: number;
  orientation: string;
  inclinationDegrees: number | null;
};

const moduleByCategory: Record<string, string> = {
  chauffage: "heating", pac: "heating", "chauffe-eau": "heating",
  volets: "access", "éclairage": "access", eclairage: "access",
  portail: "access", garage: "access", piscine: "pool", spa: "pool",
  borne: "vehicle", recharge: "vehicle", véhicule: "vehicle", vehicule: "vehicle",
  solaire: "solar", batterie: "solar", caméra: "access", camera: "access", alarme: "access",
};

function numeric(value: unknown) {
  const match = String(value ?? "").replace(",", ".").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : 0;
}

export function peakWattsFromErp(value: unknown) {
  const amount = numeric(value);
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  return Math.round(amount <= 100 ? amount * 1000 : amount);
}

export function batteryCapacityWhFromErp(value: unknown) {
  const text = String(value ?? "");
  if (!text.trim()) return 0;
  const amount = numeric(text);
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  return Math.round(/mwh/i.test(text) ? amount * 1_000_000 : /kwh/i.test(text) || amount < 100 ? amount * 1000 : amount);
}

function splitValues(value: unknown) {
  return String(value ?? "")
    .split(/\s*(?:\+|\/|;|\||\bet\b)\s*/i)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function solarArraysFromErp(detail: ErpDossierDetail): SolarArrayConfiguration[] {
  const orientations = splitValues(detail.orientation);
  const inclinations = splitValues(detail.inclination);
  const count = Math.max(1, orientations.length, inclinations.length);
  const total = peakWattsFromErp(detail.solarPeakKwc);
  const base = count ? Math.floor(total / count) : total;
  return Array.from({ length: count }, (_, index) => ({
    id: `pan-${index + 1}`,
    label: count > 1 ? `Pan ${index + 1}` : "Toiture principale",
    peakWatts: index === count - 1 ? Math.max(0, total - base * (count - 1)) : base,
    orientation: orientations[index] ?? orientations[0] ?? "À vérifier",
    inclinationDegrees: inclinations[index] ? numeric(inclinations[index]) : inclinations[0] ? numeric(inclinations[0]) : null,
  }));
}

function slug(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 70) || "equipement";
}

function iconFor(category: string) {
  const normalized = category.toLowerCase();
  if (normalized.includes("piscine") || normalized.includes("spa")) return "≈";
  if (normalized.includes("chauff")) return "♨";
  if (normalized.includes("borne") || normalized.includes("véhic")) return "▣";
  if (normalized.includes("solaire") || normalized.includes("batter")) return "☀";
  if (normalized.includes("cam") || normalized.includes("alarme")) return "◉";
  if (normalized.includes("volet") || normalized.includes("portail")) return "▤";
  return "◇";
}

export function plannedDevicesFromErp(devices: ErpDevice[]) {
  return devices.map((device, index) => {
    const category = String(device.category || "Autre").trim();
    const brand = String(device.brand || "Marque à confirmer").trim();
    const model = String(device.model || category).trim();
    return {
      id: `erp-${slug(`${category}-${brand}-${model}-${index}`)}`,
      brand,
      model,
      category,
      protocol: "À confirmer",
      level: "Expert" as const,
      method: "Recherche automatique puis validation sur place",
      prerequisites: String(device.comments || "Modèle et accès réseau à vérifier lors de la pose"),
      estimatedMinutes: 15,
      icon: iconFor(category),
      quantity: Math.max(1, Math.min(99, Math.round(Number(device.quantity) || 1))),
      room: category.includes("Piscine") ? "Piscine" : "Maison",
      status: "À préparer" as const,
    };
  });
}

export function modulesFromErp(devices: ErpDevice[], hasSolar = true) {
  const modules = new Set(["home"]);
  if (hasSolar) modules.add("solar");
  for (const device of devices) {
    const category = String(device.category || "").toLowerCase();
    for (const [needle, module] of Object.entries(moduleByCategory)) {
      if (category.includes(needle)) modules.add(module);
    }
  }
  return [...modules];
}
