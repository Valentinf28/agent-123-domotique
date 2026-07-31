import {
  queueAgentAutomationDelete,
  queueAgentAutomationState,
} from "../../../../lib/agent-home";
import {
  portalApiAuthorized,
  portalApiError,
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
    const { publicId } = await context.params;
    const result = await queueAgentAutomationState(
      publicId,
      input.enabled,
      typeof input.dossierPublicId === "string"
        ? input.dossierPublicId
        : null,
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
