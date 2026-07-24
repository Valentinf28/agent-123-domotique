import { getChatGPTUser } from "../../../chatgpt-auth";
import { createLovelaceSession } from "../../../../lib/lovelace-session";

export async function GET() {
  const user = await getChatGPTUser();
  const localDevelopment =
    process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
  const secret = process.env.HA_ACCESS_TOKEN;

  if ((!user && !localDevelopment) || !secret) {
    return Response.json({ error: "Session indisponible" }, { status: 401 });
  }

  const accessToken = await createLovelaceSession(
    secret,
    user?.email ?? "local-development",
  );
  return Response.json(
    { access_token: accessToken, expires_in: 300 },
    { headers: { "Cache-Control": "no-store" } },
  );
}
