import Stripe from "stripe";

import {
  GRACE_DAYS,
  MONTHLY_PRICE_CENTS,
  type SubscriptionStatus,
  YEARLY_PRICE_CENTS,
} from "./subscription";

export type BillingInterval = "monthly" | "yearly";

export function stripeBillingConfig() {
  const secretKey = process.env.STRIPE_SECRET_KEY?.trim();
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET?.trim();
  const monthlyPriceId = process.env.STRIPE_MONTHLY_PRICE_ID?.trim();
  const yearlyPriceId = process.env.STRIPE_YEARLY_PRICE_ID?.trim();
  return {
    secretKey,
    webhookSecret,
    monthlyPriceId,
    yearlyPriceId,
    ready: Boolean(secretKey && monthlyPriceId && yearlyPriceId),
  };
}

export function stripeClient(secretKey: string) {
  return new Stripe(secretKey, {
    httpClient: Stripe.createFetchHttpClient(),
  });
}

export function priceIdForInterval(interval: BillingInterval) {
  const config = stripeBillingConfig();
  return interval === "yearly" ? config.yearlyPriceId : config.monthlyPriceId;
}

export function priceCentsForInterval(interval: BillingInterval) {
  return interval === "yearly" ? YEARLY_PRICE_CENTS : MONTHLY_PRICE_CENTS;
}

export function intervalFromPriceId(priceId: string | null | undefined): BillingInterval {
  const config = stripeBillingConfig();
  return priceId && priceId === config.yearlyPriceId ? "yearly" : "monthly";
}

export function appStatusFromStripe(status: Stripe.Subscription.Status): SubscriptionStatus {
  switch (status) {
    case "trialing":
      return "trialing";
    case "active":
      return "active";
    case "past_due":
    case "unpaid":
    case "incomplete":
    case "incomplete_expired":
      return "past_due";
    case "paused":
      return "suspended";
    case "canceled":
      return "cancelled";
    default:
      return "not_started";
  }
}

export function stripeSubscriptionUpdate(
  subscription: Stripe.Subscription,
  now = new Date(),
  previous?: { subscriptionStatus?: string | null; graceEndsAt?: string | null },
) {
  const status = appStatusFromStripe(subscription.status);
  const interval = intervalFromPriceId(subscription.items.data[0]?.price?.id);
  const periodEnd = subscription.items.data
    .map((item) => item.current_period_end)
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => b - a)[0];
  const trialEnd = subscription.trial_end
    ? new Date(subscription.trial_end * 1000).toISOString()
    : null;
  const subscriptionEndsAt = periodEnd
    ? new Date(periodEnd * 1000).toISOString()
    : null;
  return {
    subscriptionStatus: status,
    subscriptionInterval: interval,
    subscriptionPriceCents: priceCentsForInterval(interval),
    subscriptionStartedAt: subscription.start_date
      ? new Date(subscription.start_date * 1000).toISOString()
      : now.toISOString(),
    subscriptionEndsAt: status === "cancelled" ? subscriptionEndsAt || now.toISOString() : null,
    trialEndsAt: status === "trialing" ? trialEnd : null,
    graceEndsAt: status === "past_due"
      ? previous?.subscriptionStatus === "past_due" && previous.graceEndsAt
        ? previous.graceEndsAt
        : new Date(now.getTime() + GRACE_DAYS * 86_400_000).toISOString()
      : null,
    stripeSubscriptionId: subscription.id,
    stripeCustomerId: typeof subscription.customer === "string"
      ? subscription.customer
      : subscription.customer.id,
    stripeCurrentPeriodEndsAt: subscriptionEndsAt,
    updatedAt: now.toISOString(),
  };
}

export function checkoutTrialEnd(trialEndsAt: string | null, now = new Date()) {
  if (!trialEndsAt) return undefined;
  const timestamp = Date.parse(trialEndsAt);
  // Stripe exige une échéance suffisamment éloignée pour créer un essai.
  return Number.isFinite(timestamp) && timestamp > now.getTime() + 48 * 60 * 60 * 1000
    ? Math.floor(timestamp / 1000)
    : undefined;
}
