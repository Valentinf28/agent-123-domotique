export type AssistantQuotaKind = "automation" | "energy";

// Protection mensuelle des comptes clients. Les administrateurs et comptes de
// démonstration autorisés sont exemptés au niveau de la route du Coach.
export const ASSISTANT_MONTHLY_LIMIT = 100;

export function assistantQuotaBucket(
  kind: AssistantQuotaKind,
  now = new Date(),
  timeZone = "Europe/Paris",
) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  if (!year || !month) throw new Error("INVALID_QUOTA_MONTH");
  return `${kind}:${year}-${month}`;
}

export function assistantQuotaAllows(
  current: number,
  limit = ASSISTANT_MONTHLY_LIMIT,
) {
  return current < limit;
}
