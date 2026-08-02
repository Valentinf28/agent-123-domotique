import { updatePortalDevice } from "../../../../lib/home-connector";
import {
  portalApiAuthorized,
  portalApiError,
  portalHouseAuthorized,
} from "../../../../lib/portal-api-auth";

type DeviceUpdate = {
  name?: string;
  areaPublicId?: string | null;
  visible?: boolean;
  dossierPublicId?: string;
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
    if (typeof input.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(input.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const { dossierPublicId: _dossierPublicId, ...deviceUpdate } = input;
    const allowed =
      (deviceUpdate.name === undefined || typeof deviceUpdate.name === "string") &&
      (deviceUpdate.areaPublicId === undefined ||
        deviceUpdate.areaPublicId === null ||
        typeof deviceUpdate.areaPublicId === "string") &&
      (deviceUpdate.visible === undefined || typeof deviceUpdate.visible === "boolean");
    if (!allowed || Object.keys(deviceUpdate).length === 0) {
      return Response.json(
        { error: "Informations invalides" },
        { status: 400 },
      );
    }
    const { publicId } = await context.params;
    const result = await updatePortalDevice(publicId, deviceUpdate);
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
