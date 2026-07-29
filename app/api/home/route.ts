import { getChatGPTUser } from "../../chatgpt-auth";
import { getAgentPortalHome } from "../../../lib/agent-home";

/**
 * Façade serveur du portail.
 *
 * En production, ce point d’entrée valide l’utilisateur, résout sa maison et son rôle
 * depuis le service métier, puis appelle le connecteur privé de la maison. Le navigateur
 * ne reçoit que des identifiants publics opaques et des libellés conviviaux.
 */
export async function GET(request: Request) {
  const user = await getChatGPTUser();
  const localDevelopment =
    process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
  if (!user && !localDevelopment) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }

  try {
    const dossier = new URL(request.url).searchParams.get("dossier");
    const home = await getAgentPortalHome(dossier);
    return Response.json({
      mode: "connected",
      viewer: { displayName: user?.displayName ?? "Développement local" },
      integration: "server-only",
      home,
    });
  } catch (error) {
    const code = error instanceof Error ? error.message : "CONNECTOR_ERROR";
    const status = code === "CONNECTOR_NOT_CONFIGURED" ? 503 : 502;
    return Response.json({
      error: code === "CONNECTOR_NOT_CONFIGURED"
        ? "Connecteur non configuré"
        : "Maison temporairement inaccessible",
    }, { status });
  }
}
