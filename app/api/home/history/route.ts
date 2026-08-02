import { getAgentEnergyHistory } from "../../../../lib/agent-home";
import {
  portalApiAuthorized,
  portalAuthorizedHouseIds,
} from "../../../../lib/portal-api-auth";

export async function GET(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const url = new URL(request.url);
  const date = url.searchParams.get("date") ?? "";
  const requested = url.searchParams.get("dossier");
  const allowed = await portalAuthorizedHouseIds();
  const dossier = requested || (allowed?.size === 1 ? [...allowed][0] : null);
  if (allowed && (!dossier || !allowed.has(dossier))) {
    return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
  }
  try {
    const history = await getAgentEnergyHistory(dossier, date);
    return Response.json({ date, history });
  } catch (error) {
    const code = error instanceof Error ? error.message : "HISTORY_ERROR";
    return Response.json({ error: code }, { status: code === "INVALID_DATE" ? 400 : 502 });
  }
}
