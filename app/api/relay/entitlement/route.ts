import { eq, or } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers } from "../../../../db/schema";
import { subscriptionSummary } from "../../../../lib/subscription";

function authorized(request: Request) {
  const configured = process.env.RELAY_ENTITLEMENT_SECRET || "";
  const supplied = request.headers.get("X-Relay-Authorization") ??
    request.headers.get("Authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  return Boolean(configured && supplied && configured === supplied);
}

export async function GET(request: Request) {
  if (!authorized(request)) {
    return Response.json({ error: "Relais non autorisé" }, { status: 401 });
  }
  const houseId = new URL(request.url).searchParams.get("houseId")?.trim() ?? "";
  if (!houseId || houseId.length > 160) {
    return Response.json({ error: "Maison invalide" }, { status: 400 });
  }
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(or(
      eq(installationDossiers.publicId, houseId),
      eq(installationDossiers.relayHouseId, houseId),
    )).limit(1);
  if (!dossier) {
    return Response.json({
      known: false,
      remoteAccessAllowed: false,
      status: "unknown",
    }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const summary = subscriptionSummary(dossier);
  return Response.json({
    known: true,
    houseId,
    remoteAccessAllowed: summary.remoteAccessAllowed,
    status: summary.status,
    accessEndsAt: summary.accessEndsAt,
    remainingDays: summary.remainingDays,
  }, { headers: { "Cache-Control": "no-store" } });
}
