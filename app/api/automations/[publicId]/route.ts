import {
  queueAgentAutomationDelete,
  queueAgentAutomationState,
} from "../../../../lib/agent-home";
import {
  portalApiAuthorized,
  portalApiError,
  portalHouseAuthorized,
} from "../../../../lib/portal-api-auth";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ publicId: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json(
      { error: "Authentification requise" },
      { status: 401 },
    );
  }
  try {
    const input = await request.json() as {
      enabled?: unknown;
      dossierPublicId?: unknown;
    };
    if (typeof input.enabled !== "boolean") {
      return Response.json(
        { error: "Informations invalides" },
        { status: 400 },
      );
    }
    if (typeof input.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(input.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const { publicId } = await context.params;
    const result = await queueAgentAutomationState(
      publicId,
      input.enabled,
      input.dossierPublicId,
    );
    return Response.json(result, {
      status: 202,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ publicId: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json(
      { error: "Authentification requise" },
      { status: 401 },
    );
  }
  try {
    const { publicId } = await context.params;
    const dossierPublicId =
      new URL(request.url).searchParams.get("dossier");
    if (!dossierPublicId || !await portalHouseAuthorized(dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const result = await queueAgentAutomationDelete(
      publicId,
      dossierPublicId,
    );
    return Response.json(result, {
      status: 202,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}
