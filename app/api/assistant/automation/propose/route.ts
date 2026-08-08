import { eq } from "drizzle-orm";
import { getDb } from "../../../../../db";
import { installationDossiers } from "../../../../../db/schema";
import {
  proposeSafeAutomation,
  signAutomationProposal,
} from "../../../../../lib/automation-assistant";
import { consumeAssistantRequest } from "../../../../../lib/energy-coach";
import { getAgentPortalHome } from "../../../../../lib/agent-home";
import { portalApiAuthorized, portalHouseAuthorized } from "../../../../../lib/portal-api-auth";
import { subscriptionSummary } from "../../../../../lib/subscription";

const help = {
  documentation: {
    title: "Créer une règle simple",
    steps: [
      "Vérifiez que l’appareil apparaît en ligne dans l’onglet Équipements.",
      "Indiquez une action, un appareil et une heure, ou le lever/coucher du soleil.",
      "Vous pouvez préciser tous les jours, en semaine, le week-end ou un jour particulier.",
      "Relisez toujours l’aperçu avant de confirmer.",
    ],
  },
  supportTicket: {
    available: true,
    subject: "Aide à la création d’une automatisation",
  },
};

function signingSecret() {
  return process.env.AUTOMATION_ASSISTANT_SIGNING_SECRET?.trim() ||
    process.env.OPENAI_API_KEY?.trim() || "";
}

export async function POST(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as { message?: unknown; dossierPublicId?: unknown };
    const message = typeof body.message === "string" ? body.message.trim().slice(0, 600) : "";
    const dossierPublicId = typeof body.dossierPublicId === "string" ? body.dossierPublicId : "";
    if (message.length < 3 || !dossierPublicId) {
      return Response.json({ error: "Demande incomplète", help }, { status: 400 });
    }
    const [dossier] = await getDb().select().from(installationDossiers)
      .where(eq(installationDossiers.publicId, dossierPublicId)).limit(1);
    if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
    if (!await portalHouseAuthorized(dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    if (!subscriptionSummary(dossier).remoteAccessAllowed) {
      return Response.json({
        error: "L’assistant domotique est inclus dans le forfait Premium actif.",
        code: "PREMIUM_REQUIRED",
      }, { status: 402 });
    }
    const home = await getAgentPortalHome(dossierPublicId);
    const result = proposeSafeAutomation(message, home.devices);
    if (result.status !== "ready") {
      return Response.json({ result, requiresConfirmation: false, help }, {
        headers: { "Cache-Control": "no-store" },
      });
    }
    const secret = signingSecret();
    if (!secret) {
      return Response.json({ error: "Assistant temporairement indisponible", help }, { status: 503 });
    }
    if (!await consumeAssistantRequest(dossier.id, "automation")) {
      return Response.json({
        error: "La limite mensuelle de création d’automatisations est atteinte.",
        code: "ASSISTANT_QUOTA_REACHED",
        help,
      }, { status: 429 });
    }
    const confirmationToken = await signAutomationProposal(
      result.proposal,
      dossierPublicId,
      secret,
    );
    return Response.json({
      result,
      confirmationToken,
      requiresConfirmation: true,
      expiresInSeconds: 600,
      help,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "La proposition ne peut pas être préparée", help }, { status: 502 });
  }
}
