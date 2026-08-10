type PowerSample = {
  capturedAt: string;
  vehicleWatts?: number;
  filtrationWatts?: number;
};

export type MeasuredVehicleEnergy = {
  available: boolean;
  energyWh: number;
  sampleCount: number;
  coveredMinutes: number;
};

const parisDay = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function measuredLoadEnergyToday(
  samples: PowerSample[],
  power: (sample: PowerSample) => number,
  now = new Date(),
): MeasuredVehicleEnergy {
  return measuredLoadEnergyForDay(samples, power, parisDay.format(now), now);
}

export function measuredLoadEnergyForDay(
  samples: PowerSample[],
  power: (sample: PowerSample) => number,
  day: string,
  now = new Date(),
): MeasuredVehicleEnergy {
  const today = parisDay.format(now);
  const ordered = samples
    .filter((sample) => parisDay.format(new Date(sample.capturedAt)) === day)
    .map((sample) => ({
      at: Date.parse(sample.capturedAt),
      watts: Math.max(0, Number(power(sample)) || 0),
    }))
    .filter((sample) => Number.isFinite(sample.at) && (day !== today || sample.at <= now.getTime()))
    .sort((left, right) => left.at - right.at);

  if (ordered.length < 2) {
    return { available: false, energyWh: 0, sampleCount: ordered.length, coveredMinutes: 0 };
  }

  let energyWh = 0;
  let coveredMs = 0;
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1];
    const current = ordered[index];
    const intervalMs = current.at - previous.at;
    // Ignore les longues coupures de collecte pour ne pas prolonger une
    // puissance instantanée sur une période qui n'a pas été mesurée.
    if (intervalMs <= 0 || intervalMs > 15 * 60 * 1000) continue;
    energyWh += ((previous.watts + current.watts) / 2) * intervalMs / 3_600_000;
    coveredMs += intervalMs;
  }

  return {
    available: coveredMs > 0,
    energyWh: Math.round(energyWh),
    sampleCount: ordered.length,
    coveredMinutes: Math.round(coveredMs / 60_000),
  };
}

export function measuredVehicleEnergyToday(samples: PowerSample[], now = new Date()) {
  return measuredLoadEnergyToday(samples, (sample) => sample.vehicleWatts ?? 0, now);
}

export function measuredVehicleEnergyYesterday(samples: PowerSample[], now = new Date()) {
  const parts = parisDay.format(now).split("-").map(Number);
  const previous = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] - 1, 12));
  return measuredLoadEnergyForDay(samples, (sample) => sample.vehicleWatts ?? 0, parisDay.format(previous), now);
}

export function measuredFiltrationEnergyToday(samples: PowerSample[], now = new Date()) {
  return measuredLoadEnergyToday(samples, (sample) => sample.filtrationWatts ?? 0, now);
}
