import { portalApiAdminAuthorized } from "../../../../lib/portal-api-auth";
import { searchErpDossiers } from "../../../../lib/erp-api";

export async function GET(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const query = new URL(request.url).searchParams.get("q")?.trim().slice(0, 120) ?? "";
    return Response.json({ dossiers: await searchErpDossiers(query) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const notConfigured = error instanceof Error && error.message === "ERP_NOT_CONFIGURED";
    return Response.json({
      error: notConfigured ? "La liaison ERP doit être activée par un administrateur" : "ERP temporairement indisponible",
      code: notConfigured ? "ERP_NOT_CONFIGURED" : "ERP_UNAVAILABLE",
    }, { status: notConfigured ? 503 : 502 });
  }
}
