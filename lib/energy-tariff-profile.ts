export type TariffPlan = "base" | "hp_hc" | "tempo";
export type OffPeakPeriod = { start: string; end: string };
export type EnergyTariffProfile = {
  basePrice: number | null;
  peakPrice: number | null;
  offPeakPrice: number | null;
};

const clockPattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

export function sanitizeTariffPlan(value: unknown): TariffPlan {
  return value === "hp_hc" || value === "tempo" ? value : "base";
}

export function sanitizeOffPeakPeriods(value: unknown): OffPeakPeriod[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 4).flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Record<string, unknown>;
    const start = String(item.start ?? "").trim();
    const end = String(item.end ?? "").trim();
    return clockPattern.test(start) && clockPattern.test(end) && start !== end ? [{ start, end }] : [];
  });
}

function price(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 5
    ? Math.round(parsed * 100_000) / 100_000 : null;
}

export function sanitizeEnergyTariff(value: unknown): EnergyTariffProfile {
  const item = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return {
    basePrice: price(item.basePrice),
    peakPrice: price(item.peakPrice),
    offPeakPrice: price(item.offPeakPrice),
  };
}

export function parseStoredTariff<T>(value: string, sanitize: (parsed: unknown) => T, fallback: T): T {
  try { return sanitize(JSON.parse(value)); } catch { return fallback; }
}
