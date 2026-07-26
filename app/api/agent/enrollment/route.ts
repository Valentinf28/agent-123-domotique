import { and, asc, eq, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, agentEnrollmentCodes, installationDossiers } from "../../../../db/schema";
import { enrollmentCode, sha256 } from "../../../../lib/agent-auth";
import { portalApiAuthorized } from "../../../../lib/portal-api-auth";

async function activeDossier() {
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.status, "preparation"))
    .orderBy(asc(installationDossiers.id)).limit(1);
  return dossier ?? null;
}

export async function GET() {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const dossier = await activeDossier();
  if (!dossier) return Response.json({ agent: null });
  const [agent] = await getDb().select().from(agentBoxes)
    .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
  return Response.json({
    agent: agent ? {
      publicId: agent.publicId, label: agent.label, status: agent.status,
      haVersion: agent.haVersion, inventoryCount: agent.inventoryCount,
      lastSeenAt: agent.lastSeenAt,
      inventory: (() => {
        try { return JSON.parse(agent.inventoryJson) as unknown[]; } catch { return []; }
      })(),
    } : null,
  }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST() {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const dossier = await activeDossier();
  if (!dossier) return Response.json({ error: "Aucun dossier en préparation" }, { status: 404 });
  const db = getDb();
  const [existingAgent] = await db.select().from(agentBoxes)
    .where(eq(agentBoxes.dossierId, dossier.id)).limit(1);
  if (existingAgent) {
    return Response.json({ error: "Une box est déjà associée à ce dossier" }, { status: 409 });
  }
  const code = enrollmentCode();
  const expiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  await db.delete(agentEnrollmentCodes).where(and(
    eq(agentEnrollmentCodes.dossierId, dossier.id),
    isNull(agentEnrollmentCodes.usedAt),
  ));
  await db.insert(agentEnrollmentCodes).values({
    publicId: crypto.randomUUID(),
    dossierId: dossier.id,
    codeHash: await sha256(code),
    expiresAt,
  });
  return Response.json({ code, expiresAt }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
