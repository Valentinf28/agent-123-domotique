export type SolarForecastSlot = {
  startsAt: string;
  estimatedWh: number;
};

export type PredictiveEnergySettings = {
  batteryCapacityWh: number;
  batteryReservePercent: number;
};

export type FlexibleLoadInput = {
  id: string;
  label: string;
  category: string;
  powerWatts: number;
  minimumRunMinutes: number;
  alreadyRunning: boolean;
  needed: boolean;
  needReason?: string;
};

export type PredictiveEnergyInput = {
  now: Date;
  batteryPercent: number;
  baseLoadWatts: number;
  forecast: SolarForecastSlot[];
  settings: PredictiveEnergySettings;
  load: FlexibleLoadInput;
};

export type PredictiveEnergyPlan = {
  loadId: string;
  loadLabel: string;
  loadCategory: string;
  status:
    | "ready_now"
    | "scheduled"
    | "protected"
    | "already_running"
    | "no_need"
    | "needs_forecast"
    | "needs_setup";
  headline: string;
  explanation: string;
  forecastRemainingWh: number;
  forecastNextSixHoursWh: number;
  flexibleLoadEnergyWh: number;
  projectedMinimumBatteryPercent: number;
  projectedEndBatteryPercent: number;
  expectedAvoidedExportWh: number;
  suggestedStartAt: string | null;
  peakAt: string | null;
  confidence: "low" | "medium" | "high";
};

type SimulationResult = {
  minimumBatteryPercent: number;
  endBatteryPercent: number;
  exportedWh: number;
  importedWh: number;
};

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function finite(value: number, fallback = 0) {
  return Number.isFinite(value) ? value : fallback;
}

function slotDurationHours(slots: SolarForecastSlot[], index: number) {
  const start = Date.parse(slots[index].startsAt);
  const next = slots[index + 1] ? Date.parse(slots[index + 1].startsAt) : start + 60 * 60 * 1000;
  return clamp((next - start) / 3_600_000, 0.25, 1.5);
}

function simulateBattery(
  input: PredictiveEnergyInput,
  slots: SolarForecastSlot[],
  flexibleLoadWh: number,
): SimulationResult {
  const capacity = input.settings.batteryCapacityWh;
  const reserveWh = capacity * input.settings.batteryReservePercent / 100;
  let batteryWh = capacity * clamp(input.batteryPercent, 0, 100) / 100;
  let minimumWh = batteryWh;
  let exportedWh = 0;
  let importedWh = 0;
  for (let index = 0; index < slots.length; index += 1) {
    const duration = slotDurationHours(slots, index);
    const baseLoadWh = input.baseLoadWatts * duration;
    const flexibleWh = index === 0 ? flexibleLoadWh : 0;
    batteryWh += slots[index].estimatedWh - baseLoadWh - flexibleWh;
    if (batteryWh > capacity) {
      exportedWh += batteryWh - capacity;
      batteryWh = capacity;
    }
    if (batteryWh < reserveWh) {
      importedWh += reserveWh - batteryWh;
      batteryWh = reserveWh;
    }
    minimumWh = Math.min(minimumWh, batteryWh);
  }
  return {
    minimumBatteryPercent: capacity ? Math.round(minimumWh / capacity * 100) : 0,
    endBatteryPercent: capacity ? Math.round(batteryWh / capacity * 100) : 0,
    exportedWh: Math.round(exportedWh),
    importedWh: Math.round(importedWh),
  };
}

function plan(
  input: PredictiveEnergyInput,
  partial: Partial<PredictiveEnergyPlan>,
): PredictiveEnergyPlan {
  return {
    loadId: input.load.id,
    loadLabel: input.load.label,
    loadCategory: input.load.category,
    status: "needs_setup",
    headline: "Configuration énergétique à compléter",
    explanation: `Le technicien doit renseigner la batterie et la puissance de ${input.load.label}.`,
    forecastRemainingWh: 0,
    forecastNextSixHoursWh: 0,
    flexibleLoadEnergyWh: 0,
    projectedMinimumBatteryPercent: Math.round(input.batteryPercent),
    projectedEndBatteryPercent: Math.round(input.batteryPercent),
    expectedAvoidedExportWh: 0,
    suggestedStartAt: null,
    peakAt: null,
    confidence: "low",
    ...partial,
  };
}

export function buildPredictiveEnergyPlan(input: PredictiveEnergyInput): PredictiveEnergyPlan {
  const settings = input.settings;
  if (
    settings.batteryCapacityWh <= 0 ||
    input.load.powerWatts <= 0 ||
    input.load.minimumRunMinutes < 15
  ) {
    return plan(input, {});
  }
  const now = input.now.getTime();
  const slots = input.forecast
    .map((slot) => ({
      startsAt: slot.startsAt,
      estimatedWh: Math.max(0, finite(slot.estimatedWh)),
    }))
    .filter((slot) => {
      const start = Date.parse(slot.startsAt);
      return Number.isFinite(start) && start >= now - 90 * 60 * 1000 && start <= now + 24 * 60 * 60 * 1000;
    })
    .sort((left, right) => Date.parse(left.startsAt) - Date.parse(right.startsAt));
  if (!slots.length) {
    return plan(input, {
      status: "needs_forecast",
      headline: "Prévision solaire à connecter",
      explanation: "Ajoutez Forecast.Solar dans Home Assistant puis associez-le au tableau Énergie.",
    });
  }

  const flexibleLoadEnergyWh = Math.round(
    input.load.powerWatts * input.load.minimumRunMinutes / 60,
  );
  const forecastRemainingWh = Math.round(
    slots.reduce((sum, slot) => sum + slot.estimatedWh, 0),
  );
  const forecastNextSixHoursWh = Math.round(
    slots
      .filter((slot) => Date.parse(slot.startsAt) <= now + 6 * 60 * 60 * 1000)
      .reduce((sum, slot) => sum + slot.estimatedWh, 0),
  );
  const peak = slots.reduce((best, slot) =>
    slot.estimatedWh > best.estimatedWh ? slot : best, slots[0]);
  const confidence = slots.length >= 12 ? "high" : slots.length >= 5 ? "medium" : "low";
  const withoutFlexibleLoad = simulateBattery(input, slots, 0);
  const withFlexibleLoadNow = simulateBattery(input, slots, flexibleLoadEnergyWh);
  const common = {
    forecastRemainingWh,
    forecastNextSixHoursWh,
    flexibleLoadEnergyWh,
    projectedMinimumBatteryPercent: withFlexibleLoadNow.minimumBatteryPercent,
    projectedEndBatteryPercent: withFlexibleLoadNow.endBatteryPercent,
    expectedAvoidedExportWh: Math.min(flexibleLoadEnergyWh, withoutFlexibleLoad.exportedWh),
    peakAt: peak.startsAt,
    confidence,
  } satisfies Partial<PredictiveEnergyPlan>;

  if (!input.load.needed) {
    return plan(input, {
      ...common,
      status: "no_need",
      headline: `${input.load.label} n’a pas besoin de démarrer`,
      explanation: input.load.needReason || "Le besoin prévu est déjà couvert.",
    });
  }
  if (input.load.alreadyRunning) {
    return plan(input, {
      ...common,
      status: "already_running",
      headline: `${input.load.label} est déjà en fonctionnement`,
      explanation: "Le moteur continue de surveiller la réserve batterie et la production prévue.",
    });
  }

  const capacity = settings.batteryCapacityWh;
  const reserveMarginWh = capacity * 0.05;
  const energyAboveReserveWh = capacity *
    Math.max(0, input.batteryPercent - settings.batteryReservePercent) / 100;
  const sixHourBaseWh = input.baseLoadWatts * Math.min(6, slots.length);
  const afternoonCanRefill =
    forecastNextSixHoursWh >= sixHourBaseWh + flexibleLoadEnergyWh ||
    withoutFlexibleLoad.exportedWh >= flexibleLoadEnergyWh * 0.4;
  const batteryCanFundEarlyStart =
    energyAboveReserveWh >= flexibleLoadEnergyWh + reserveMarginWh &&
    withFlexibleLoadNow.minimumBatteryPercent >= settings.batteryReservePercent;

  if (batteryCanFundEarlyStart && afternoonCanRefill) {
    const forecastKwh = (forecastNextSixHoursWh / 1000).toFixed(1).replace(".", ",");
    return plan(input, {
      ...common,
      status: "ready_now",
      headline: "Démarrage anticipé conseillé",
      explanation: `${input.load.label} peut fonctionner ${input.load.minimumRunMinutes} min maintenant : ${forecastKwh} kWh solaires sont prévus dans les six prochaines heures et la réserve restera protégée.`,
      suggestedStartAt: input.now.toISOString(),
    });
  }

  const scheduled = slots.find((slot, index) => {
    const duration = slotDurationHours(slots, index);
    return slot.estimatedWh >=
      input.baseLoadWatts * duration + input.load.powerWatts * duration * 0.7;
  });
  if (scheduled) {
    return plan(input, {
      ...common,
      status: "scheduled",
      headline: "Attendre le créneau solaire",
      explanation: `La batterie ne doit pas être sollicitée maintenant. ${input.load.label} pourra démarrer lorsque la production couvrira l’essentiel de sa puissance.`,
      suggestedStartAt: scheduled.startsAt,
    });
  }

  return plan(input, {
    ...common,
    status: "protected",
    headline: "Réserve batterie protégée",
    explanation: "La prévision ne permet pas de garantir un cycle complet sans achat réseau ou batterie trop basse.",
  });
}
