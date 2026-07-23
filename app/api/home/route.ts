import { getChatGPTUser } from "../../chatgpt-auth";

/**
 * Façade serveur du portail.
 *
 * En production, ce point d’entrée valide l’utilisateur, résout sa maison et son rôle
 * depuis le service métier, puis appelle le connecteur privé de la maison. Le navigateur
 * ne reçoit que des identifiants publics opaques et des libellés conviviaux.
 */
export async function GET() {
  const user = await getChatGPTUser();
  if (!user) return Response.json({ error: "Authentification requise" }, { status: 401 });

  return Response.json({
    mode: "demo",
    viewer: { displayName: user.displayName },
    integration: "server-only",
  });
}
