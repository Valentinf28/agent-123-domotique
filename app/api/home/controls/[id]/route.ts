import { queueAgentControl } from "../../../../../lib/agent-home";
import {
  portalApiAuthorized,
  portalApiError,
  portalHouseAuthorized,
} from "../../../../../lib/portal-api-auth";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const { id } = await context.params;
    const body = await request.json() as {
      active?: unknown;
      dossierPublicId?: unknown;
    };
    if (typeof body.active !== "boolean") throw new Error("INVALID_STATE");
    const dossierPublicId = typeof body.dossierPublicId === "string"
      ? body.dossierPublicId
      : null;
    if (!dossierPublicId || !await portalHouseAuthorized(dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const result = await queueAgentControl(id, body.active, dossierPublicId);
    return Response.json(result, {
      status: 202,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}
