import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers, mobilePairingCodes, plannedDevices } from "../../../../db/schema";
import { sha256 } from "../../../../lib/agent-auth";
import {
  normalizeEnabledModules,
  normalizeSolarInstalledPowerWp,
} from "../../../../lib/client-modules.js";
import { subscriptionSummary } from "../../../../lib/subscription";

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
    await db.update(mobilePairingCodes).set({ usedAt: new Date().toISOString() })
      .where(eq(mobilePairingCodes.id, pairing.id));
    const origin = new URL(request.url).origin;
    return Response.json({
      installationId: dossier.publicId,
      houseName: dossier.customerName || "Ma Maison",
      portalUrl: `${origin}/ma-maison`,
      apiBaseUrl: `${origin}/api`,
      subscription: subscriptionSummary(dossier),
      tariffPlan: dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
      offPeakPeriods: offPeakPeriodsFromDossier(dossier.offPeakPeriodsJson),
      solarInstalledPowerWp: normalizeSolarInstalledPowerWp(dossier.solarPeakWatts),
      modules,
      views,
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
