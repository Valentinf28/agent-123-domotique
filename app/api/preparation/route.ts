import { and, asc, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { installationDossiers, plannedDevices } from "../../../db/schema";
import { portalApiAuthorized } from "../../../lib/portal-api-auth";

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
};

const allowedLevels = new Set(["Automatique", "Assistée", "Expert"]);
const allowedStatuses = new Set(["À préparer", "Prêt", "Détecté", "Associé", "Testé", "Bloqué"]);
const allowedModules = new Set(["home", "solar", "heating", "access", "pool", "vehicle"]);
const defaultModules = ["home", "solar", "heating", "access", "vehicle"];

function publicId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
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
  const [created] = await db.insert(installationDossiers).values({
    publicId: publicId("installation"),
    reference: "DOSSIER-PILOTE",
    customerName: "Maison pilote",
  }).returning();
  return created;
}

export async function GET(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const dossier = await activeDossier(request);
    const items = await getDb().select().from(plannedDevices)
      .where(eq(plannedDevices.dossierId, dossier.id))
      .orderBy(asc(plannedDevices.id));
    return Response.json({
      dossier: {
        publicId: dossier.publicId, reference: dossier.reference, customerName: dossier.customerName,
        enabledModules: (() => {
          try { return JSON.parse(dossier.enabledModules) as string[]; } catch { return defaultModules; }
        })(),
      },
      items: items.map((item) => ({
        id: item.catalogId, brand: item.brand, model: item.model, category: item.category,
        protocol: item.protocol, level: item.compatibilityLevel, method: item.connectionMethod,
        prerequisites: item.prerequisites, estimatedMinutes: item.estimatedMinutes,
        icon: item.icon, quantity: item.quantity, room: item.room, status: item.status,
      })),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Préparation temporairement indisponible" }, { status: 503 });
  }
}

export async function PUT(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as { items?: PlannedDevicePayload[]; enabledModules?: string[]; dossierPublicId?: string };
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
      };
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
    await db.delete(plannedDevices).where(eq(plannedDevices.dossierId, dossier.id));
    if (items.length) {
      await db.insert(plannedDevices).values(items.map((item) => ({
        ...item, publicId: publicId("planned"), dossierId: dossier.id,
      })));
    }
    await db.update(installationDossiers).set({
      enabledModules: JSON.stringify(enabledModules),
      updatedAt: new Date().toISOString(),
    })
      .where(and(eq(installationDossiers.id, dossier.id), eq(installationDossiers.status, "preparation")));
    return Response.json({ saved: true, count: items.length, enabledModules });
  } catch (error) {
    const invalid = error instanceof Error && error.message === "INVALID_ITEM";
    return Response.json(
      { error: invalid ? "Un équipement est incomplet" : "Enregistrement impossible" },
      { status: invalid ? 400 : 503 },
    );
  }
}
