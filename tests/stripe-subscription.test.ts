import assert from "node:assert/strict";
import test from "node:test";

import {
  appStatusFromStripe,
  checkoutTrialEnd,
  priceCentsForInterval,
  stripeSubscriptionUpdate,
} from "../lib/stripe-subscription";
import type Stripe from "stripe";

test("les tarifs Premium correspondent aux offres commerciales", () => {
  assert.equal(priceCentsForInterval("monthly"), 990);
  assert.equal(priceCentsForInterval("yearly"), 9900);
});

test("les statuts Stripe pilotent correctement l’accès distant", () => {
  assert.equal(appStatusFromStripe("trialing"), "trialing");
  assert.equal(appStatusFromStripe("active"), "active");
  assert.equal(appStatusFromStripe("past_due"), "past_due");
  assert.equal(appStatusFromStripe("unpaid"), "past_due");
  assert.equal(appStatusFromStripe("paused"), "suspended");
  assert.equal(appStatusFromStripe("canceled"), "cancelled");
});

test("un essai en cours est transmis à Stripe seulement s’il reste plus de 48 h", () => {
  const now = new Date("2026-08-02T10:00:00.000Z");
  assert.equal(
    checkoutTrialEnd("2026-08-12T10:00:00.000Z", now),
    Date.parse("2026-08-12T10:00:00.000Z") / 1000,
  );
  assert.equal(checkoutTrialEnd("2026-08-03T10:00:00.000Z", now), undefined);
  assert.equal(checkoutTrialEnd(null, now), undefined);
});

function subscription(status: Stripe.Subscription.Status): Stripe.Subscription {
  return {
    id: "sub_test",
    status,
    customer: "cus_test",
    start_date: 1_700_000_000,
    trial_end: null,
    items: {
      data: [{ current_period_end: 1_800_000_000, price: { id: "price_test" } }],
    },
  } as unknown as Stripe.Subscription;
}

test("un webhook Stripe rejoué ne prolonge jamais la période de grâce", () => {
  const now = new Date("2026-08-02T10:00:00.000Z");
  const first = stripeSubscriptionUpdate(subscription("past_due"), now);
  assert.equal(first.graceEndsAt, "2026-08-09T10:00:00.000Z");

  const replayed = stripeSubscriptionUpdate(
    subscription("past_due"),
    new Date("2026-08-04T10:00:00.000Z"),
    first,
  );
  assert.equal(replayed.graceEndsAt, first.graceEndsAt);
});
