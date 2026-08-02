import { queueAgentAutomationCreate } from "../../../../../lib/agent-home";
import { verifyAutomationProposal } from "../../../../../lib/automation-assistant";
import {
  portalApiAuthorized,
  portalApiError,
  portalHouseAuthorized,
} from "../../../../../lib/portal-api-auth";

function signingSecret() {
  return process.env.AUTOMATION_ASSISTANT_SIGNING_SECRET?.trim() ||
    process.env.OPENAI_API_KEY?.trim() || "";
}

export async function POST(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as { confirmationToken?: unknown; confirmed?: unknown };
    if (body.confirmed !== true || typeof body.confirmationToken !== "string") {
      return Response.json({
        error: "La validation explicite de l’aperçu est obligatoire.",
        code: "EXPLICIT_CONFIRMATION_REQUIRED",
      }, { status: 409 });
    }
    const secret = signingSecret();
    if (!secret) return Response.json({ error: "Assistant temporairement indisponible" }, { status: 503 });
    const payload = await verifyAutomationProposal(body.confirmationToken, secret);
    if (!payload) {
      return Response.json({
        error: "Cet aperçu a expiré. Préparez une nouvelle proposition avant de confirmer.",
        code: "INVALID_OR_EXPIRED_PROPOSAL",
      }, { status: 409 });
    }
    if (!await portalHouseAuthorized(payload.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const result = await queueAgentAutomationCreate({
      name: payload.rule.name,
      time: payload.rule.time,
      publicDeviceId: payload.rule.publicDeviceId,
      desiredActive: payload.rule.desiredActive,
    }, payload.dossierPublicId);
    return Response.json({
      ...result,
      message: "Automatisation envoyée à la Green Box.",
      rule: payload.rule,
    }, { status: 202, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return portalApiError(error);
  }
}
