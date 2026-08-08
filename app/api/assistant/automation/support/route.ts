import { eq } from "drizzle-orm";
import { getDb } from "../../../../../db";
import { installationDossiers } from "../../../../../db/schema";
import { portalApiAuthorized, portalHouseAuthorized } from "../../../../../lib/portal-api-auth";

function supportConfig() {
  return {
    url: process.env.SUPPORT_TICKET_WEBHOOK_URL?.trim() ?? "",
    token: process.env.SUPPORT_TICKET_WEBHOOK_TOKEN?.trim() ?? "",
  };
}

export async function POST(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as {
      dossierPublicId?: unknown;
      message?: unknown;
      reason?: unknown;
    };
    const dossierPublicId = typeof body.dossierPublicId === "string" ? body.dossierPublicId.trim() : "";
    const message = typeof body.message === "string" ? body.message.trim().slice(0, 600) : "";
    const reason = typeof body.reason === "string" ? body.reason.trim().slice(0, 600) : "";
    if (!dossierPublicId || message.length < 3) {
      return Response.json({ error: "Demande de support incomplète" }, { status: 400 });
    }
    const [dossier] = await getDb().select({ publicId: installationDossiers.publicId })
      .from(installationDossiers)
      .where(eq(installationDossiers.publicId, dossierPublicId))
      .limit(1);
    if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
    if (!await portalHouseAuthorized(dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }

    const config = supportConfig();
    if (!config.url) {
      return Response.json({
        error: "La création de ticket sera disponible dès que le canal support sera configuré.",
        code: "SUPPORT_NOT_CONFIGURED",
      }, { status: 503 });
    }
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.token) headers.Authorization = `Bearer ${config.token}`;
    const response = await fetch(config.url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        source: "assistant-domotique",
        dossierPublicId,
        subject: "Aide à la création d’une automatisation",
        description: message,
        reason,
      }),
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) throw new Error("support");
    return Response.json({ message: "Votre demande a été transmise au support." }, { status: 202 });
  } catch {
    return Response.json({ error: "Le support n’est pas joignable pour le moment" }, { status: 502 });
  }
}
