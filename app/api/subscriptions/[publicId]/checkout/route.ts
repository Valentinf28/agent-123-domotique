import { eq } from "drizzle-orm";

import { getDb } from "../../../../../db";
import { installationDossiers } from "../../../../../db/schema";
import { portalApiAuthorized, portalHouseAuthorized } from "../../../../../lib/portal-api-auth";
import {
  checkoutTrialEnd,
  priceIdForInterval,
  stripeBillingConfig,
  stripeClient,
  type BillingInterval,
} from "../../../../../lib/stripe-subscription";

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

  const body = await request.json().catch(() => ({})) as { interval?: BillingInterval };
  const interval: BillingInterval = body.interval === "yearly" ? "yearly" : "monthly";
  const config = stripeBillingConfig();
  const priceId = priceIdForInterval(interval);
  if (!config.ready || !config.secretKey || !priceId) {
    return Response.json({
      error: "Le paiement Premium n’est pas encore activé sur ce portail",
      code: "STRIPE_NOT_CONFIGURED",
    }, { status: 503 });
  }

  const origin = new URL(request.url).origin;
  const stripe = stripeClient(config.secretKey);
  const trialEnd = dossier.subscriptionStatus === "trialing"
    ? checkoutTrialEnd(dossier.trialEndsAt)
    : undefined;
  try {
    const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: priceId, quantity: 1 }],
    client_reference_id: publicId,
    customer: dossier.stripeCustomerId || undefined,
    success_url: `${origin}/ma-maison?abonnement=confirme`,
    cancel_url: `${origin}/ma-maison?abonnement=annule`,
    metadata: { publicId, interval },
    subscription_data: {
      metadata: { publicId, interval },
      ...(trialEnd ? { trial_end: trialEnd } : {}),
    },
    allow_promotion_codes: true,
    });
    if (!session.url) {
      return Response.json({ error: "Paiement indisponible" }, { status: 502 });
    }
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
