import { queueAgentAutomationCreate } from "../../../lib/agent-home";
import {
  portalApiAuthorized,
  portalApiError,
  portalHouseAuthorized,
} from "../../../lib/portal-api-auth";

export async function POST(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json(
      { error: "Authentification requise" },
      { status: 401 },
    );
  }
  try {
    const body = await request.json() as {
      name?: unknown;
      time?: unknown;
      publicDeviceId?: unknown;
      desiredActive?: unknown;
      dossierPublicId?: unknown;
    };
    if (
      typeof body.name !== "string" ||
      typeof body.time !== "string" ||
      typeof body.publicDeviceId !== "string" ||
      typeof body.desiredActive !== "boolean"
    ) {
      return Response.json(
        { error: "Informations invalides" },
        { status: 400 },
      );
    }
    if (typeof body.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(body.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const result = await queueAgentAutomationCreate(
      {
        name: body.name,
        time: body.time,
        publicDeviceId: body.publicDeviceId,
        desiredActive: body.desiredActive,
      },
      body.dossierPublicId,
    );
    return Response.json(result, {
      status: 202,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return portalApiError(error);
  }
}
