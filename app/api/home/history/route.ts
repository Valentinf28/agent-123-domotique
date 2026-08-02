import { getChatGPTUser } from "../../../chatgpt-auth";
import { getAgentEnergyHistory } from "../../../../lib/agent-home";

export async function GET(request: Request) {
  const user = await getChatGPTUser();
  const localDevelopment = process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
  if (!user && !localDevelopment) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const url = new URL(request.url);
  const date = url.searchParams.get("date") ?? "";
  const dossier = url.searchParams.get("dossier");
  try {
    const history = await getAgentEnergyHistory(dossier, date);
    return Response.json({ date, history });
  } catch (error) {
    const code = error instanceof Error ? error.message : "HISTORY_ERROR";
    return Response.json({ error: code }, { status: code === "INVALID_DATE" ? 400 : 502 });
  }
}
