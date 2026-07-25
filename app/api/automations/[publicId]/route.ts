import {
  deletePortalAutomation,
  setPortalAutomationEnabled,
} from "../../../../lib/home-connector";
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
    const input = await request.json() as { enabled?: unknown };
    if (typeof input.enabled !== "boolean") {
      return Response.json(
        { error: "Informations invalides" },
        { status: 400 },
      );
    }
    const { publicId } = await context.params;
    const result = await setPortalAutomationEnabled(publicId, input.enabled);
    return Response.json(result, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}

export async function DELETE(
  _request: Request,
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
    const result = await deletePortalAutomation(publicId);
    return Response.json(result, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}
