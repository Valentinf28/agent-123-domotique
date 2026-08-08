type BatteryHistorySample = {
  capturedAt: string;
  batteryWatts: number;
  solarWatts: number;
};

function localBucket(date: Date) {
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  return hour * 2 + Math.floor(minute / 30);
}

function median(values: number[]) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export type BatteryNightOutlook = {
  available: boolean;
  confidence: "measured" | "limited";
  usableWh: number;
  expectedWh: number;
  marginWh: number;
  horizonHours: number;
  nextSolarAt: string | null;
  holdsUntilSolar: boolean | null;
  observedNights: number;
};

export function buildBatteryNightOutlook(input: {
  now: Date;
  batteryCapacityWh: number;
  batteryPercent: number;
  reservePercent: number;
  currentDischargeWatts: number;
  history: BatteryHistorySample[];
  nextSolarAt?: string | null;
}): BatteryNightOutlook {
  const capacity = Math.max(0, input.batteryCapacityWh);
  const usableWh = capacity * Math.max(0, input.batteryPercent - input.reservePercent) / 100;
  const parsedSolar = input.nextSolarAt ? Date.parse(input.nextSolarAt) : Number.NaN;
  const fallbackEnd = input.now.getTime() + 7 * 60 * 60_000;
  const end = Number.isFinite(parsedSolar) && parsedSolar > input.now.getTime()
    ? Math.min(parsedSolar, input.now.getTime() + 12 * 60 * 60_000)
    : fallbackEnd;
  const horizonHours = Math.max(0, (end - input.now.getTime()) / 3_600_000);
  const valuesByBucket = new Map<number, number[]>();
  const nights = new Set<string>();
  const dayFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit",
  });
  for (const sample of input.history) {
    if (sample.solarWatts >= 100) continue;
    const discharge = Math.max(0, sample.batteryWatts);
    const bucket = localBucket(new Date(sample.capturedAt));
    const values = valuesByBucket.get(bucket) ?? [];
    values.push(discharge);
    valuesByBucket.set(bucket, values);
    nights.add(dayFormatter.format(new Date(sample.capturedAt)));
  }

  let profiledSteps = 0;
  let expectedWh = 0;
  const stepMs = 30 * 60_000;
  for (let cursor = input.now.getTime(); cursor < end; cursor += stepMs) {
    const durationHours = Math.min(stepMs, end - cursor) / 3_600_000;
    const historical = valuesByBucket.get(localBucket(new Date(cursor))) ?? [];
    if (historical.length >= 3) {
      expectedWh += median(historical) * durationHours;
      profiledSteps += 1;
    } else {
      expectedWh += Math.max(0, input.currentDischargeWatts) * durationHours;
    }
  }
  const totalSteps = Math.max(1, Math.ceil((end - input.now.getTime()) / stepMs));
  const confidence = profiledSteps / totalSteps >= 0.75 && nights.size >= 5 ? "measured" : "limited";
  const available = capacity > 0 && input.batteryPercent > 0 && horizonHours > 0;
  const marginWh = usableWh - expectedWh;
  return {
    available,
    confidence,
    usableWh,
    expectedWh,
    marginWh,
    horizonHours,
    nextSolarAt: Number.isFinite(parsedSolar) ? new Date(parsedSolar).toISOString() : null,
    holdsUntilSolar: available ? marginWh >= 0 : null,
    observedNights: nights.size,
  };
}
