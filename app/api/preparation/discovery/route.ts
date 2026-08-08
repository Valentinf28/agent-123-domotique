import { and, asc, eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, installationDossiers, plannedDevices } from "../../../../db/schema";
import { portalApiAdminAuthorized } from "../../../../lib/portal-api-auth";
import { ENERGY_PROFILE } from "../../../../lib/energy-profile.generated";
import { HOUSE_BINDINGS } from "../../../../lib/house-bindings.generated";
import { analyzeHouseBindings } from "../../../../shared/house-binding-discovery.js";
import { analyzeProvisioning, entityIsShowroomOnly } from "../../../../shared/provisioning-discovery.js";

type Confirmation = { key?: string; entityId?: string };
type BindingConfirmation = { key?: string; entityId?: string };

const bindingProfile = { ...ENERGY_PROFILE, ...HOUSE_BINDINGS };

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

function bindingsFrom(value: string) {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, string> : {};
  } catch {
    return {};
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
  const bindings = analyzeHouseBindings({
    profile: bindingProfile,
    inventory,
    isShowroom: dossier.reference.toUpperCase().includes("SHOWROOM"),
    overrides: bindingsFrom(dossier.entityBindingsJson),
  });
  return { dossier, agent, items, inventory, report: { ...report, bindings } };
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
      bindingConfirmations?: BindingConfirmation[];
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
    const isShowroom = context.dossier.reference.toUpperCase().includes("SHOWROOM");
    const savedBindings = bindingsFrom(context.dossier.entityBindingsJson);
    const bindingConfirmations = Array.isArray(body.bindingConfirmations) ? body.bindingConfirmations.slice(0, 100) : [];
    for (const confirmation of bindingConfirmations) {
      const key = String(confirmation.key ?? "");
      const entityId = String(confirmation.entityId ?? "");
      if (!(key in bindingProfile)) {
        return Response.json({ error: `Rôle de capteur invalide : ${key}` }, { status: 400 });
      }
      const entity = context.inventory.find((candidate: { entityId?: string }) => candidate.entityId === entityId);
      if (!entity || (!isShowroom && entityIsShowroomOnly(entity))) {
        return Response.json({ error: `Capteur invalide pour ${key}` }, { status: 400 });
      }
      savedBindings[key] = entityId;
    }
    if (bindingConfirmations.length) {
      await db.update(installationDossiers).set({
        entityBindingsJson: JSON.stringify(savedBindings),
        updatedAt: new Date().toISOString(),
      }).where(eq(installationDossiers.id, context.dossier.id));
    }

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

    const bindingReport = analyzeHouseBindings({
      profile: bindingProfile,
      inventory: context.inventory,
      isShowroom,
      overrides: savedBindings,
    });
    return Response.json({
      saved: true,
      applied,
      report: { ...context.report, bindings: bindingReport },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Découverte impossible" }, { status: 400 });
  }
}
