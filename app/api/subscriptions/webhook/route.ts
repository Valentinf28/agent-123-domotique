import Stripe from "stripe";
import { eq, or } from "drizzle-orm";

import { getDb } from "../../../../db";
import { installationDossiers } from "../../../../db/schema";
import {
  stripeBillingConfig,
  stripeClient,
  stripeSubscriptionUpdate,
} from "../../../../lib/stripe-subscription";

async function synchronize(subscription: Stripe.Subscription, occurredAt = new Date()) {
  const publicId = subscription.metadata.publicId?.trim();
  const customerId = typeof subscription.customer === "string"
    ? subscription.customer
    : subscription.customer.id;
  const condition = publicId
    ? eq(installationDossiers.publicId, publicId)
    : or(
      eq(installationDossiers.stripeSubscriptionId, subscription.id),
      eq(installationDossiers.stripeCustomerId, customerId),
    );
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(condition).limit(1);
  if (!dossier) return false;
  if (publicId && dossier.stripeCustomerId && dossier.stripeCustomerId !== customerId) {
    return false;
  }
  await getDb().update(installationDossiers)
    .set(stripeSubscriptionUpdate(subscription, occurredAt, dossier))
    .where(eq(installationDossiers.id, dossier.id));
  return true;
}

export async function POST(request: Request) {
  const config = stripeBillingConfig();
  const signature = request.headers.get("stripe-signature");
  if (!config.secretKey || !config.webhookSecret || !signature) {
    return Response.json({ error: "Webhook non configuré" }, { status: 503 });
  }
  const stripe = stripeClient(config.secretKey);
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      await request.text(),
      signature,
      config.webhookSecret,
      undefined,
      Stripe.createSubtleCryptoProvider(),
    );
  } catch {
    return Response.json({ error: "Signature invalide" }, { status: 400 });
  }

  if (
    event.type === "customer.subscription.created" ||
    event.type === "customer.subscription.updated" ||
    event.type === "customer.subscription.deleted"
  ) {
    await synchronize(event.data.object as Stripe.Subscription, new Date(event.created * 1000));
  } else if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;
    if (typeof session.subscription === "string") {
      const subscription = await stripe.subscriptions.retrieve(session.subscription);
      await synchronize(subscription, new Date(event.created * 1000));
    }
  }
  return Response.json({ received: true });
}
