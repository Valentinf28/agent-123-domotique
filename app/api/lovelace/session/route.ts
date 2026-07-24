import { getChatGPTUser } from "../../../chatgpt-auth";

export async function GET() {
  const user = await getChatGPTUser();
  const localDevelopment =
    process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";

  if (!user && !localDevelopment) {
    return Response.json(
      { ready: false, message: "Votre session a expiré. Reconnectez-vous au portail." },
      { status: 401 },
    );
  }

  if (!process.env.HA_BASE_URL || !process.env.HA_ACCESS_TOKEN) {
    return Response.json(
      { ready: false, message: "La connexion sécurisée de cette maison est incomplète." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  return Response.json(
    { ready: true, dashboardPath: "/ma-maison/ha/lovelace/0?kiosk&external_auth=1" },
    { headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
  );
}
