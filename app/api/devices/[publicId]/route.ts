import { updatePortalDevice } from "../../../../lib/home-connector";
import {
  portalApiAuthorized,
  portalApiError,
} from "../../../../lib/portal-api-auth";

type DeviceUpdate = {
  name?: string;
  areaPublicId?: string | null;
  visible?: boolean;
};

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
    const input = await request.json() as DeviceUpdate;
    const allowed =
      (input.name === undefined || typeof input.name === "string") &&
      (input.areaPublicId === undefined ||
        input.areaPublicId === null ||
        typeof input.areaPublicId === "string") &&
      (input.visible === undefined || typeof input.visible === "boolean");
    if (!allowed || Object.keys(input).length === 0) {
      return Response.json(
        { error: "Informations invalides" },
        { status: 400 },
      );
    }
    const { publicId } = await context.params;
    const result = await updatePortalDevice(publicId, input);
    return Response.json(result, {
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    return portalApiError(error);
  }
}
