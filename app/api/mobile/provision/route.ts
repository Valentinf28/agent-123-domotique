import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, installationDossiers, mobilePairingCodes, plannedDevices } from "../../../../db/schema";
import { randomSecret, sha256 } from "../../../../lib/agent-auth";
import { ENERGY_PROFILE } from "../../../../lib/energy-profile.generated";
import { HOUSE_BINDINGS } from "../../../../lib/house-bindings.generated";
import {
  normalizeEnabledModules,
  normalizeSolarInstalledPowerWp,
} from "../../../../lib/client-modules.js";
import { subscriptionSummary } from "../../../../lib/subscription";
import { relayHouseIdForDossier } from "../../../../lib/relay-house";
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

function offPeakPeriodsFromDossier(value: string) {
  try {
    const periods = JSON.parse(value);
    return Array.isArray(periods) ? periods : [];
  } catch {
    return [];
  }
}

function inventoryFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function bindingsFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, string> : {};
  } catch {
    return {};
  }
}

function measuredLoadsFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed
      .filter((load) => load?.enabled !== false
        && load?.showInConsumption !== false
        && typeof load?.powerEntityId === "string"
        && load.powerEntityId.includes("."))
      .map((load) => ({
        id: String(load.id || load.powerEntityId),
        name: String(load.name || "Équipement"),
        category: String(load.category || "other"),
        icon: String(load.icon || "ϟ"),
        powerEntityId: load.powerEntityId,
      })) : [];
  } catch {
    return [];
  }
}

async function mobileRelayCredential(dossier: typeof installationDossiers.$inferSelect) {
  const relayBaseUrl = process.env.RELAY_BASE_URL?.trim().replace(/\/+$/, "");
  const relaySecret = process.env.RELAY_CAMERA_SECRET?.trim();
  if (!relayBaseUrl || !relaySecret) throw new Error("Relais mobile non configuré");
  const relayHouseId = relayHouseIdForDossier(dossier);
  const response = await fetch(
    `${relayBaseUrl}/v1/internal/client-credential/${encodeURIComponent(relayHouseId)}`,
    { method: "POST", headers: { "X-Relay-Authorization": relaySecret } },
  );
  if (!response.ok) throw new Error("Accès mobile indisponible");
  const credential = await response.json() as { token?: string };
  if (!credential.token) throw new Error("Accès mobile incomplet");
  const relayUrl = new URL(relayBaseUrl);
  relayUrl.protocol = relayUrl.protocol === "https:" ? "wss:" : "ws:";
  relayUrl.pathname = "/v1/client";
  relayUrl.search = "";
  relayUrl.hash = "";
  return { relayHouseId, relayUrl: relayUrl.toString(), accessToken: credential.token };
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { code?: string };
    const code = String(body.code ?? "").trim().toUpperCase();
    if (!/^[A-Z2-9]{8}$/.test(code)) return Response.json({ error: "Code invalide" }, { status: 400 });
    const db = getDb();
    const [pairing] = await db.select().from(mobilePairingCodes).where(and(
      eq(mobilePairingCodes.codeHash, await sha256(code)),
      isNull(mobilePairingCodes.usedAt),
      gt(mobilePairingCodes.expiresAt, new Date().toISOString()),
    )).limit(1);
    if (!pairing) return Response.json({ error: "Code expiré ou déjà utilisé" }, { status: 410 });
    const [dossier] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.id, pairing.dossierId)).limit(1);
    if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
    const modules = normalizeEnabledModules(dossier.enabledModules);
    const views = modules
      .filter((module): module is keyof typeof viewCatalog => module in viewCatalog)
      .map(module => viewCatalog[module]);
    const configuredDevices = await db.select().from(plannedDevices)
      .where(eq(plannedDevices.dossierId, dossier.id));
    const [agent] = await db.select().from(agentBoxes)
      .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
    const bindingReport = analyzeHouseBindings({
      profile: { ...ENERGY_PROFILE, ...HOUSE_BINDINGS },
      inventory: inventoryFrom(agent?.inventoryJson ?? "[]"),
      isShowroom: dossier.reference.toUpperCase().includes("SHOWROOM"),
      essentialKeys: [...Object.keys(ENERGY_PROFILE), ...Object.keys(HOUSE_BINDINGS)],
      overrides: bindingsFrom(dossier.entityBindingsJson),
    });
    const relayCredential = await mobileRelayCredential(dossier);
    const configurationToken = randomSecret();
    await db.update(mobilePairingCodes).set({
      usedAt: new Date().toISOString(),
      configurationTokenHash: await sha256(configurationToken),
    })
      .where(eq(mobilePairingCodes.id, pairing.id));
    const origin = new URL(request.url).origin;
    return Response.json({
      installationId: dossier.publicId,
      ...relayCredential,
      houseName: dossier.customerName || "Ma Maison",
      portalUrl: `${origin}/ma-maison`,
      apiBaseUrl: `${origin}/api`,
      configurationUrl: `${origin}/api/mobile/configuration`,
      configurationToken,
      subscription: subscriptionSummary(dossier),
      tariffPlan: dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
      offPeakPeriods: offPeakPeriodsFromDossier(dossier.offPeakPeriodsJson),
      allowGridExport: dossier.allowGridExport,
      solarInstalledPowerWp: normalizeSolarInstalledPowerWp(dossier.solarPeakWatts),
      modules,
      views,
      bindings: bindingReport.bindings,
      measuredLoads: measuredLoadsFrom(dossier.flexibleLoadsJson),
      configuredDevices: configuredDevices
        .filter((device) => Boolean(device.matchedEntityId))
        .map((device) => ({
          catalogId: device.catalogId,
          name: device.matchedEntityName || `${device.brand} ${device.model}`,
          room: device.room,
          category: device.category,
          publicId: publicDeviceId(device.matchedEntityId as string),
        })),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Association impossible" }, { status: 503 });
  }
}
