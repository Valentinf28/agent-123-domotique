import { and, asc, eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, installationDossiers, plannedDevices } from "../../../../db/schema";
import { portalApiAdminAuthorized } from "../../../../lib/portal-api-auth";
import { analyzeProvisioning } from "../../../../shared/provisioning-discovery.js";

type Confirmation = { key?: string; entityId?: string };

async function dossierFromRequest(request: Request, body?: Record<string, unknown>) {
  const requested = String(body?.dossierPublicId ?? new URL(request.url).searchParams.get("dossier") ?? "");
  const db = getDb();
  if (requested) {
    const [selected] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.publicId, requested)).limit(1);
    if (selected) return selected;
  }
  const [active] = await db.select().from(installationDossiers)
    .where(eq(installationDossiers.status, "preparation"))
    .orderBy(asc(installationDossiers.id)).limit(1);
  return active ?? null;
}

function inventoryFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function discoveryContext(request: Request, body?: Record<string, unknown>) {
  const dossier = await dossierFromRequest(request, body);
  if (!dossier) return null;
  const db = getDb();
  const [agent] = await db.select().from(agentBoxes)
    .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
  const items = await db.select().from(plannedDevices)
    .where(eq(plannedDevices.dossierId, dossier.id)).orderBy(asc(plannedDevices.id));
  const inventory = inventoryFrom(agent?.inventoryJson ?? "[]");
  const report = analyzeProvisioning({
    items,
    inventory,
    isShowroom: dossier.reference.toUpperCase().includes("SHOWROOM"),
  });
  return { dossier, agent, items, inventory, report };
}

export async function GET(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  const context = await discoveryContext(request);
  if (!context) return Response.json({ error: "Dossier introuvable" }, { status: 404 });
  return Response.json({
    agentOnline: context.agent?.status === "online",
    report: context.report,
  }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const body = await request.json() as {
      dossierPublicId?: string;
      applyCertain?: boolean;
      confirmations?: Confirmation[];
    };
    const context = await discoveryContext(request, body as Record<string, unknown>);
    if (!context) return Response.json({ error: "Dossier introuvable" }, { status: 404 });
    if (!context.agent || context.agent.status !== "online") {
      return Response.json({ error: "La box doit être connectée" }, { status: 409 });
    }
    const certain = new Map(context.report.certain.map((suggestion: { key: string }) => [suggestion.key, suggestion]));
    const ambiguous = new Map(context.report.ambiguous.map((suggestion: { key: string }) => [suggestion.key, suggestion]));
    const confirmations = Array.isArray(body.confirmations) ? body.confirmations.slice(0, 100) : [];
    const confirmedByKey = new Map(confirmations.map((item) => [String(item.key ?? ""), String(item.entityId ?? "")]));
    const alreadyUsed = new Set(context.items.map((item) => item.matchedEntityId).filter(Boolean));
    const applied: Array<{ key: string; entityId: string; source: "certain" | "confirmed" }> = [];
    const db = getDb();

    for (const item of context.items) {
      if (item.matchedEntityId) continue;
      const key = `${item.catalogId}:${item.room}`;
      let chosen: { entityId: string; entityName: string } | null = null;
      let source: "certain" | "confirmed" = "certain";
      const certainSuggestion = certain.get(key) as { entityId: string; entityName: string } | undefined;
      if (body.applyCertain === true && certainSuggestion) chosen = certainSuggestion;
      const explicitlyConfirmed = confirmedByKey.get(key);
      if (explicitlyConfirmed) {
        const suggestion = ambiguous.get(key) as { candidates: Array<{ entityId: string; name: string }> } | undefined;
        const candidate = suggestion?.candidates.find((entry) => entry.entityId === explicitlyConfirmed);
        if (!candidate) {
          return Response.json({ error: `Confirmation invalide pour ${key}` }, { status: 400 });
        }
        chosen = { entityId: candidate.entityId, entityName: candidate.name };
        source = "confirmed";
      }
      if (!chosen) continue;
      if (alreadyUsed.has(chosen.entityId)) {
        return Response.json({ error: `${chosen.entityName} est déjà associé à un autre équipement` }, { status: 409 });
      }
      alreadyUsed.add(chosen.entityId);
      await db.update(plannedDevices).set({
        status: "Détecté",
        matchedEntityId: chosen.entityId,
        matchedEntityName: chosen.entityName,
        updatedAt: new Date().toISOString(),
      }).where(and(eq(plannedDevices.id, item.id), eq(plannedDevices.dossierId, context.dossier.id)));
      applied.push({ key, entityId: chosen.entityId, source });
    }

    return Response.json({
      saved: true,
      applied,
      report: context.report,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Découverte impossible" }, { status: 400 });
  }
}
