import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, installationDossiers, mobilePairingCodes, plannedDevices } from "../../../../db/schema";
import { sha256 } from "../../../../lib/agent-auth";
import { ENERGY_PROFILE } from "../../../../lib/energy-profile.generated";
import { HOUSE_BINDINGS } from "../../../../lib/house-bindings.generated";
import {
  normalizeEnabledModules,
  normalizeSolarInstalledPowerWp,
} from "../../../../lib/client-modules.js";
import { subscriptionSummary } from "../../../../lib/subscription";
import { analyzeHouseBindings } from "../../../../shared/house-binding-discovery.js";

const viewCatalog = {
  home: { key: "home", label: "Maison", icon: "home-variant-outline", path: "/app" },
  solar: { key: "solar", label: "Solaire", icon: "solar-power", path: "/app/energie" },
  heating: { key: "heating", label: "Chauffage", icon: "home-thermometer-outline", path: "/app/confort" },
  access: { key: "access", label: "Équipements", icon: "lightbulb-group-outline", path: "/app/equipements" },
  pool: { key: "pool", label: "Piscine", icon: "pool", path: "/app/piscine" },
  vehicle: { key: "vehicle", label: "Véhicule", icon: "car-electric", path: "/app/vehicule" },
} as const;

function publicDeviceId(value: string) {
  let hash = 2166136261;
  for (const char of value) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `appareil_${(hash >>> 0).toString(36)}`;
}

function parsePeriods(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseObject(value: string) {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function parseInventory(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function measuredLoads(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((load) => load?.enabled !== false && load?.showInConsumption !== false && typeof load?.powerEntityId === "string" && load.powerEntityId.includes("."))
      .map((load) => ({ id: String(load.id || load.powerEntityId), name: String(load.name || "Équipement"), category: String(load.category || "other"), icon: String(load.icon || "ϟ"), powerEntityId: load.powerEntityId })) : [];
  } catch { return []; }
}

export async function GET(request: Request) {
  const authorization = request.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const token = authorization.slice(7).trim();
  if (token.length < 40) {
    return Response.json({ error: "Authentification refusée" }, { status: 401 });
  }
  const db = getDb();
  const [pairing] = await db.select().from(mobilePairingCodes)
    .where(eq(mobilePairingCodes.configurationTokenHash, await sha256(token))).limit(1);
  if (!pairing?.usedAt) {
    return Response.json({ error: "Authentification refusée" }, { status: 401 });
  }
  const [dossier] = await db.select().from(installationDossiers)
    .where(eq(installationDossiers.id, pairing.dossierId)).limit(1);
  if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
  const [agent] = await db.select().from(agentBoxes)
    .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
  const modules = normalizeEnabledModules(dossier.enabledModules);
  const views = modules
    .filter((module): module is keyof typeof viewCatalog => module in viewCatalog)
    .map((module) => viewCatalog[module]);
  const configuredDevices = await db.select().from(plannedDevices)
    .where(eq(plannedDevices.dossierId, dossier.id));
  const bindingReport = analyzeHouseBindings({
    profile: { ...ENERGY_PROFILE, ...HOUSE_BINDINGS },
    inventory: parseInventory(agent?.inventoryJson ?? "[]"),
    isShowroom: dossier.reference.toUpperCase().includes("SHOWROOM"),
    essentialKeys: [...Object.keys(ENERGY_PROFILE), ...Object.keys(HOUSE_BINDINGS)],
    overrides: parseObject(dossier.entityBindingsJson),
  });
  return Response.json({
    installationId: dossier.publicId,
    houseName: dossier.customerName || "Ma Maison",
    subscription: subscriptionSummary(dossier),
    tariffPlan: dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
    offPeakPeriods: parsePeriods(dossier.offPeakPeriodsJson),
    allowGridExport: dossier.allowGridExport,
    solarInstalledPowerWp: normalizeSolarInstalledPowerWp(dossier.solarPeakWatts),
    modules,
    views,
    bindings: bindingReport.bindings,
    measuredLoads: measuredLoads(dossier.flexibleLoadsJson),
    configuredDevices: configuredDevices
      .filter((device) => Boolean(device.matchedEntityId))
      .map((device) => ({
        catalogId: device.catalogId,
        name: device.matchedEntityName || `${device.brand} ${device.model}`,
        room: device.room,
        category: device.category,
        publicId: publicDeviceId(device.matchedEntityId as string),
      })),
    updatedAt: dossier.updatedAt,
  }, { headers: { "Cache-Control": "no-store" } });
}
