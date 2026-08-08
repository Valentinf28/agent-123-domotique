import { eq } from "drizzle-orm";

import { getDb } from "../../../../../db";
import { installationDossiers } from "../../../../../db/schema";
import { portalApiAuthorized, portalHouseAuthorized } from "../../../../../lib/portal-api-auth";
import { stripeBillingConfig, stripeClient } from "../../../../../lib/stripe-subscription";

export async function POST(
  request: Request,
  context: { params: Promise<{ publicId: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const { publicId } = await context.params;
  if (!await portalHouseAuthorized(publicId)) {
    return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
  }
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.publicId, publicId)).limit(1);
  if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
  if (!dossier.stripeCustomerId) {
    return Response.json({ error: "Aucun abonnement à gérer" }, { status: 409 });
  }
  const config = stripeBillingConfig();
  if (!config.secretKey) {
    return Response.json({
      error: "Le paiement Premium n’est pas encore activé sur ce portail",
      code: "STRIPE_NOT_CONFIGURED",
    }, { status: 503 });
  }
  const stripe = stripeClient(config.secretKey);
  try {
    const session = await stripe.billingPortal.sessions.create({
      customer: dossier.stripeCustomerId,
      return_url: `${new URL(request.url).origin}/ma-maison`,
    });
    return Response.json({ url: session.url }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({
      error: "Le service de paiement est momentanément indisponible",
      code: "STRIPE_UNAVAILABLE",
    }, { status: 502 });
  }
}
