export const TRIAL_DAYS = 30;
export const GRACE_DAYS = 7;
export const MONTHLY_PRICE_CENTS = 790;
export const YEARLY_PRICE_CENTS = 7900;

export type SubscriptionStatus =
  | "not_started"
  | "trialing"
  | "active"
  | "past_due"
  | "suspended"
  | "cancelled";

type SubscriptionRecord = {
  subscriptionStatus: string;
  subscriptionPriceCents: number;
  subscriptionInterval: string;
  trialStartedAt: string | null;
  trialEndsAt: string | null;
  graceEndsAt: string | null;
  subscriptionStartedAt: string | null;
  subscriptionEndsAt: string | null;
};

const timestamp = (value: string | null) => value ? Date.parse(value) : Number.NaN;

export function addDays(date: Date, days: number) {
  return new Date(date.getTime() + days * 24 * 60 * 60 * 1000);
}

export function subscriptionSummary(record: SubscriptionRecord, now = new Date()) {
  const status = record.subscriptionStatus as SubscriptionStatus;
  const nowMs = now.getTime();
  const trialValid = status === "trialing" && timestamp(record.trialEndsAt) > nowMs;
  const activeValid = status === "active" &&
    (!record.subscriptionEndsAt || timestamp(record.subscriptionEndsAt) > nowMs);
  const graceValid = status === "past_due" && timestamp(record.graceEndsAt) > nowMs;
  const remoteAccessAllowed = trialValid || activeValid || graceValid;
  const accessEndsAt = trialValid
    ? record.trialEndsAt
    : graceValid
    ? record.graceEndsAt
    : activeValid
    ? record.subscriptionEndsAt
    : null;
  const remainingDays = accessEndsAt
    ? Math.max(0, Math.ceil((timestamp(accessEndsAt) - nowMs) / 86_400_000))
    : null;
  return {
    status,
    remoteAccessAllowed,
    accessEndsAt,
    remainingDays,
    trialStartedAt: record.trialStartedAt,
    trialEndsAt: record.trialEndsAt,
    graceEndsAt: record.graceEndsAt,
    subscriptionStartedAt: record.subscriptionStartedAt,
    subscriptionEndsAt: record.subscriptionEndsAt,
    priceCents: record.subscriptionPriceCents,
    interval: record.subscriptionInterval,
  };
}
