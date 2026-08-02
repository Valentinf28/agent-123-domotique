import { and, asc, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { installationDossiers, plannedDevices } from "../../../db/schema";
import { portalApiAdminAuthorized } from "../../../lib/portal-api-auth";

type PlannedDevicePayload = {
  id?: string;
  brand?: string;
  model?: string;
  category?: string;
  protocol?: string;
  level?: string;
  method?: string;
  prerequisites?: string;
  estimatedMinutes?: number;
  icon?: string;
  quantity?: number;
  room?: string;
  status?: string;
  matchedEntityId?: string | null;
  matchedEntityName?: string | null;
};

type EnergyConfigurationPayload = {
  solarPeakWatts?: number;
  solarArrays?: SolarArrayPayload[];
  batteryCapacityWh?: number;
  batteryReservePercent?: number;
  flexibleLoads?: FlexibleLoadPayload[];
  tariffPlan?: string;
  offPeakPeriods?: OffPeakPeriodPayload[];
};

type SolarArrayPayload = {
  id?: string;
  label?: string;
  peakWatts?: number;
  orientation?: string;
  inclinationDegrees?: number | null;
};

type OffPeakPeriodPayload = {
  id?: string;
  label?: string;
  start?: string;
  end?: string;
};

type FlexibleLoadPayload = {
  id?: string;
  name?: string;
  category?: string;
  icon?: string;
  powerWatts?: number;
  minimumRunMinutes?: number;
  priority?: number;
  enabled?: boolean;
};

const allowedLevels = new Set(["Automatique", "Assistée", "Expert"]);
const allowedStatuses = new Set(["À préparer", "Prêt", "Détecté", "Associé", "Testé", "Bloqué"]);
const allowedModules = new Set(["home", "solar", "heating", "access", "pool", "vehicle"]);
const defaultModules = ["home", "solar", "heating", "access", "vehicle"];

function publicId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

function boundedInteger(value: unknown, fallback: number, minimum: number, maximum: number) {
  const numeric = value === undefined ? fallback : Number(value);
  const safeValue = Number.isFinite(numeric) ? numeric : fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(safeValue)));
}

function flexibleLoadsFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function offPeakPeriodsFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function solarArraysFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function sanitizeSolarArrays(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 20).map((raw, index) => {
    const item = raw && typeof raw === "object" ? raw as SolarArrayPayload : {};
    const id = String(item.id ?? `pan-${index + 1}`).toLowerCase().replace(/[^a-z0-9_-]+/g, "-").slice(0, 40);
    const label = String(item.label ?? `Pan ${index + 1}`).trim().slice(0, 80);
    if (!id || !label) throw new Error("INVALID_SOLAR_ARRAY");
    const rawInclination = item.inclinationDegrees;
    return {
      id,
      label,
      peakWatts: boundedInteger(item.peakWatts, 0, 0, 100_000),
      orientation: String(item.orientation ?? "À vérifier").trim().slice(0, 60) || "À vérifier",
      inclinationDegrees: rawInclination === null || rawInclination === undefined || rawInclination === ""
        ? null
        : boundedInteger(rawInclination, 0, 0, 90),
    };
  });
}

function sanitizeOffPeakPeriods(value: unknown) {
  if (!Array.isArray(value)) return [];
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  return value.slice(0, 4).map((raw, index) => {
    const item = raw && typeof raw === "object" ? raw as OffPeakPeriodPayload : {};
    const start = String(item.start ?? "").trim();
    const end = String(item.end ?? "").trim();
    if (!timePattern.test(start) || !timePattern.test(end) || start === end) {
      throw new Error("INVALID_OFF_PEAK_PERIOD");
    }
    return {
      id: String(item.id ?? `hc-${index + 1}`).toLowerCase().replace(/[^a-z0-9_-]+/g, "-").slice(0, 40),
      label: String(item.label ?? `Plage ${index + 1}`).trim().slice(0, 40) || `Plage ${index + 1}`,
      start,
      end,
    };
  });
}

function sanitizeFlexibleLoads(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 20).map((raw, index) => {
    const item = raw && typeof raw === "object" ? raw as FlexibleLoadPayload : {};
    const id = String(item.id ?? `appareil-${index + 1}`)
      .toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
    const name = String(item.name ?? "").trim().slice(0, 80);
    if (!id || !name) throw new Error("INVALID_FLEXIBLE_LOAD");
    return {
      id,
      name,
      category: String(item.category ?? "other").trim().slice(0, 40) || "other",
      icon: String(item.icon ?? "ϟ").slice(0, 8),
      powerWatts: boundedInteger(item.powerWatts, 0, 0, 50_000),
      minimumRunMinutes: boundedInteger(item.minimumRunMinutes, 60, 15, 720),
      priority: boundedInteger(item.priority, 3, 1, 5),
      enabled: item.enabled === true,
    };
  });
}

async function activeDossier(request?: Request, requestedPublicId?: string) {
  const db = getDb();
  const publicIdValue = requestedPublicId || (request ? new URL(request.url).searchParams.get("dossier") : "");
  if (publicIdValue) {
    const [selected] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.publicId, publicIdValue)).limit(1);
    if (selected) return selected;
  }
  const [existing] = await db.select().from(installationDossiers)
    .where(eq(installationDossiers.status, "preparation"))
    .orderBy(asc(installationDossiers.id)).limit(1);
  if (existing) return existing;
  const dossierPublicId = publicId("installation");
  const [created] = await db.insert(installationDossiers).values({
    publicId: dossierPublicId,
    relayHouseId: dossierPublicId,
    reference: "DOSSIER-PILOTE",
    customerName: "Maison pilote",
  }).returning();
  return created;
}

export async function GET(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const dossier = await activeDossier(request);
    const items = await getDb().select().from(plannedDevices)
      .where(eq(plannedDevices.dossierId, dossier.id))
      .orderBy(asc(plannedDevices.id));
    return Response.json({
      dossier: {
        publicId: dossier.publicId, reference: dossier.reference, customerName: dossier.customerName,
        customerAddress: dossier.customerAddress,
        erpDossierId: dossier.erpDossierId,
        erpImportedAt: dossier.erpImportedAt,
        enabledModules: (() => {
          try { return JSON.parse(dossier.enabledModules) as string[]; } catch { return defaultModules; }
        })(),
        energyConfiguration: {
          solarPeakWatts: dossier.solarPeakWatts,
          solarArrays: solarArraysFrom(dossier.solarArraysJson),
          batteryCapacityWh: dossier.batteryCapacityWh,
          batteryReservePercent: dossier.batteryReservePercent,
          flexibleLoads: flexibleLoadsFrom(dossier.flexibleLoadsJson),
          tariffPlan: dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
          offPeakPeriods: offPeakPeriodsFrom(dossier.offPeakPeriodsJson),
        },
      },
      items: items.map((item) => ({
        id: item.catalogId, brand: item.brand, model: item.model, category: item.category,
        protocol: item.protocol, level: item.compatibilityLevel, method: item.connectionMethod,
        prerequisites: item.prerequisites, estimatedMinutes: item.estimatedMinutes,
        icon: item.icon, quantity: item.quantity, room: item.room, status: item.status,
        matchedEntityId: item.matchedEntityId, matchedEntityName: item.matchedEntityName,
      })),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Préparation temporairement indisponible" }, { status: 503 });
  }
}

export async function PUT(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const body = await request.json() as {
      items?: PlannedDevicePayload[];
      enabledModules?: string[];
      dossierPublicId?: string;
      energyConfiguration?: EnergyConfigurationPayload;
    };
    if (!Array.isArray(body.items) || body.items.length > 200) {
      return Response.json({ error: "Liste invalide" }, { status: 400 });
    }
    const items = body.items.map((item) => {
      const quantity = Math.min(99, Math.max(1, Math.round(Number(item.quantity) || 1)));
      const estimatedMinutes = Math.min(180, Math.max(0, Math.round(Number(item.estimatedMinutes) || 0)));
      const level = String(item.level ?? "");
      const status = String(item.status ?? "");
      const clean = {
        catalogId: String(item.id ?? "").slice(0, 100),
        brand: String(item.brand ?? "").trim().slice(0, 80),
        model: String(item.model ?? "").trim().slice(0, 120),
        category: String(item.category ?? "").trim().slice(0, 80),
        protocol: String(item.protocol ?? "").trim().slice(0, 40),
        compatibilityLevel: allowedLevels.has(level) ? level : "Expert",
        connectionMethod: String(item.method ?? "").trim().slice(0, 180),
        prerequisites: String(item.prerequisites ?? "").trim().slice(0, 300),
        estimatedMinutes, icon: String(item.icon ?? "◇").slice(0, 8),
        quantity, room: String(item.room ?? "Maison").trim().slice(0, 80) || "Maison",
        status: allowedStatuses.has(status) ? status : "À préparer",
        matchedEntityId: String(item.matchedEntityId ?? "").trim().slice(0, 180) || null,
        matchedEntityName: String(item.matchedEntityName ?? "").trim().slice(0, 180) || null,
      };
      if (clean.matchedEntityId && !/^[a-z0-9_]+\.[a-z0-9_]+$/i.test(clean.matchedEntityId)) {
        throw new Error("INVALID_ENTITY");
      }
      if (!clean.catalogId || !clean.brand || !clean.model) throw new Error("INVALID_ITEM");
      return clean;
    });
    const keys = new Set(items.map((item) => `${item.catalogId}:${item.room}`));
    if (keys.size !== items.length) {
      return Response.json({ error: "Un appareil ne peut apparaître deux fois dans la même pièce" }, { status: 400 });
    }
    const dossier = await activeDossier(undefined, String(body.dossierPublicId ?? ""));
    const db = getDb();
    const requestedModules = Array.isArray(body.enabledModules) ? body.enabledModules : (() => {
      try { return JSON.parse(dossier.enabledModules) as string[]; } catch { return defaultModules; }
    })();
    const enabledModules = [...new Set(["home", ...requestedModules.filter(module => allowedModules.has(module))])];
    const requestedEnergy = body.energyConfiguration ?? {};
    const existingFlexibleLoads = flexibleLoadsFrom(dossier.flexibleLoadsJson);
    const energyConfiguration = {
      solarPeakWatts: boundedInteger(requestedEnergy.solarPeakWatts, dossier.solarPeakWatts, 0, 100_000),
      solarArrays: requestedEnergy.solarArrays === undefined
        ? solarArraysFrom(dossier.solarArraysJson)
        : sanitizeSolarArrays(requestedEnergy.solarArrays),
      batteryCapacityWh: boundedInteger(requestedEnergy.batteryCapacityWh, dossier.batteryCapacityWh, 0, 500_000),
      batteryReservePercent: boundedInteger(requestedEnergy.batteryReservePercent, dossier.batteryReservePercent, 5, 80),
      flexibleLoads: requestedEnergy.flexibleLoads === undefined
        ? existingFlexibleLoads
        : sanitizeFlexibleLoads(requestedEnergy.flexibleLoads),
      tariffPlan: requestedEnergy.tariffPlan === undefined
        ? dossier.tariffPlan
        : requestedEnergy.tariffPlan === "hp_hc" ? "hp_hc" : "base",
      offPeakPeriods: requestedEnergy.offPeakPeriods === undefined
        ? offPeakPeriodsFrom(dossier.offPeakPeriodsJson)
        : sanitizeOffPeakPeriods(requestedEnergy.offPeakPeriods),
    };
    const persistedItems = items.map((item) => ({
      ...item, publicId: publicId("planned"), dossierId: dossier.id,
    }));
    const insertStatements = [];
    for (let index = 0; index < persistedItems.length; index += 4) {
      insertStatements.push(
        db.insert(plannedDevices).values(persistedItems.slice(index, index + 4)),
      );
    }
    const dossierUpdate = db.update(installationDossiers).set({
      enabledModules: JSON.stringify(enabledModules),
      solarPeakWatts: energyConfiguration.solarPeakWatts,
      solarArraysJson: JSON.stringify(energyConfiguration.solarArrays),
      batteryCapacityWh: energyConfiguration.batteryCapacityWh,
      batteryReservePercent: energyConfiguration.batteryReservePercent,
      flexibleLoadsJson: JSON.stringify(energyConfiguration.flexibleLoads),
      tariffPlan: energyConfiguration.tariffPlan,
      offPeakPeriodsJson: JSON.stringify(energyConfiguration.offPeakPeriods),
      updatedAt: new Date().toISOString(),
    })
      .where(and(eq(installationDossiers.id, dossier.id), eq(installationDossiers.status, "preparation")));
    await db.batch([
      db.delete(plannedDevices).where(eq(plannedDevices.dossierId, dossier.id)),
      ...insertStatements,
      dossierUpdate,
    ]);
    return Response.json({ saved: true, count: items.length, enabledModules, energyConfiguration });
  } catch (error) {
    const invalid = error instanceof Error &&
      ["INVALID_ITEM", "INVALID_ENTITY", "INVALID_FLEXIBLE_LOAD", "INVALID_OFF_PEAK_PERIOD", "INVALID_SOLAR_ARRAY"].includes(error.message);
    return Response.json(
      { error: invalid ? "Un équipement ou son association est invalide" : "Enregistrement impossible" },
      { status: invalid ? 400 : 503 },
    );
  }
}
