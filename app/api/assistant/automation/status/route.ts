import { and, desc, eq } from "drizzle-orm";
import { getDb } from "../../../../../db";
import { agentCommands, installationDossiers } from "../../../../../db/schema";
import {
  portalApiAuthorized,
  portalHouseAuthorized,
} from "../../../../../lib/portal-api-auth";

export async function GET(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const dossierPublicId = new URL(request.url).searchParams.get("dossier")?.trim() ?? "";
  if (!dossierPublicId || !await portalHouseAuthorized(dossierPublicId)) {
    return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
  }
  const db = getDb();
  const [dossier] = await db.select().from(installationDossiers)
    .where(eq(installationDossiers.publicId, dossierPublicId)).limit(1);
  if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });

  const commands = await db.select().from(agentCommands).where(and(
    eq(agentCommands.dossierId, dossier.id),
    eq(agentCommands.action, "ha.automation.create"),
  )).orderBy(desc(agentCommands.id)).limit(10);
  return Response.json({ commands: commands.flatMap((command) => {
    const createdAt = Date.parse(command.createdAt);
    const visibilityMs = command.status === "failed"
      ? 24 * 60 * 60 * 1000
      : command.status === "completed"
      ? 15 * 60 * 1000
      : 60 * 60 * 1000;
    if (Number.isFinite(createdAt) && createdAt < Date.now() - visibilityMs) return [];
    try {
      const rule = JSON.parse(command.payloadJson) as Record<string, unknown>;
      return [{
        id: command.publicId,
        status: command.status,
        error: command.error,
        name: String(rule.name ?? "Nouvelle automatisation"),
        trigger: rule.triggerType === "time" ? `Tous les jours à ${String(rule.time ?? "")}` : "Horaire solaire",
        action: "Création sur la box 1.2.3. Home",
      }];
    } catch {
      return [];
    }
  }) }, { headers: { "Cache-Control": "no-store" } });
}
