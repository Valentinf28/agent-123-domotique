import { getChatGPTUser } from "../app/chatgpt-auth";

export async function portalApiAuthorized() {
  const user = await getChatGPTUser();
  const localDevelopment =
    process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
  return Boolean(user || localDevelopment);
}

export function portalApiError(error: unknown) {
  const code = error instanceof Error ? error.message : "CONNECTOR_ERROR";
  const notFound = code.endsWith("_NOT_FOUND");
  const invalid = code.startsWith("INVALID_");
  return Response.json(
    {
      error: notFound
        ? "Élément introuvable"
        : invalid
        ? "Informations invalides"
        : "La modification n’a pas pu être appliquée",
    },
    {
      status: notFound ? 404 : invalid ? 400 : 502,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
