export type AssistantQuotaKind = "automation" | "energy";

// Le Coach est le service central de l’abonnement Premium. Cent échanges sont
// trop vite atteints lors de dialogues et de relances normales ; 1 000 garde
// une protection contre les abus sans bloquer un usage client quotidien.
export const ASSISTANT_MONTHLY_LIMIT = 1_000;

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
