export type SolarForecastSlot = {
  startsAt: string;
  estimatedWh: number;
};

export type SolarForecastConfidence = "low" | "medium" | "high";

export type AdaptiveSolarForecastInput = {
  now: Date;
  forecast: SolarForecastSlot[];
  actualSolarWatts: number;
  forecastSolarWatts: number;
  actualTodayWh: number;
  forecastTodayWh: number;
  forecastRemainingWh: number;
  cloudCoverPercent?: number | null;
};

export type AdaptiveSolarForecast = {
  rawSlots: SolarForecastSlot[];
  prudentSlots: SolarForecastSlot[];
  rawTodayWh: number;
  prudentTodayWh: number;
  rawRemainingWh: number;
  prudentRemainingWh: number;
  correctionPercent: number;
  confidence: SolarForecastConfidence;
  explanation: string | null;
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
  forecastConfidence?: SolarForecastConfidence;
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
  confidence: SolarForecastConfidence;
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

function formatEnergyKwh(valueWh: number) {
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(valueWh / 1_000);
}

export function buildAdaptiveSolarForecast(
  input: AdaptiveSolarForecastInput,
): AdaptiveSolarForecast {
  const now = input.now.getTime();
  const rawSlots = input.forecast
    .map((slot) => ({
      startsAt: slot.startsAt,
      estimatedWh: Math.max(0, finite(slot.estimatedWh)),
    }))
    .filter((slot) => {
      const start = Date.parse(slot.startsAt);
      return Number.isFinite(start) &&
        start >= now - 90 * 60 * 1000 &&
        start <= now + 24 * 60 * 60 * 1000;
    })
    .sort((left, right) => Date.parse(left.startsAt) - Date.parse(right.startsAt));

  const baselineFactor = 0.88;
  const actualSolarWatts = Math.max(0, finite(input.actualSolarWatts));
  const forecastSolarWatts = Math.max(0, finite(input.forecastSolarWatts));
  const actualTodayWh = Math.max(0, finite(input.actualTodayWh));
  const forecastTodayWh = Math.max(0, finite(input.forecastTodayWh));
  const forecastRemainingWh = Math.max(0, finite(input.forecastRemainingWh));
  const localHourFormatter = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    hourCycle: "h23",
  });
  const localHour = Number(
    localHourFormatter.formatToParts(input.now).find((part) => part.type === "hour")?.value,
  );
  // Certains compteurs journaliers ne se remettent à zéro que quelques
  // minutes après minuit. Ne jamais additionner la production de la veille à
  // la prévision du nouveau jour.
  const alignedActualTodayWh = localHour < 3 && forecastTodayWh > 0 && actualTodayWh > forecastTodayWh
    ? 0
    : actualTodayWh;
  const expectedElapsedWh = Math.max(0, forecastTodayWh - forecastRemainingWh);
  const cloudCover = input.cloudCoverPercent == null
    ? null
    : clamp(finite(input.cloudCoverPercent), 0, 100);
  const liveRatio = forecastSolarWatts >= 150
    ? clamp(actualSolarWatts / forecastSolarWatts, 0.08, 1.1)
    : null;
  const elapsedRatio = expectedElapsedWh >= 250
    ? clamp(alignedActualTodayWh / expectedElapsedWh, 0.08, 1.1)
    : null;

  let nearTermFactor = baselineFactor;
  if (liveRatio !== null && elapsedRatio !== null) {
    nearTermFactor = liveRatio * 0.65 + elapsedRatio * 0.35;
  } else if (liveRatio !== null) {
    nearTermFactor = liveRatio;
  } else if (elapsedRatio !== null) {
    nearTermFactor = elapsedRatio;
  }
  if (cloudCover !== null && cloudCover >= 85) {
    nearTermFactor = Math.min(nearTermFactor, 0.65);
  }
  nearTermFactor = clamp(nearTermFactor, 0.08, 0.95);

  const dayProgress = forecastTodayWh > 0
    ? clamp(expectedElapsedWh / forecastTodayWh, 0, 1)
    : 0;
  const elapsedInfluence = elapsedRatio === null
    ? 0
    : clamp(dayProgress * 0.8, 0.15, 0.45);
  const farTermFactor = elapsedRatio === null
    ? baselineFactor
    : clamp(
      baselineFactor * (1 - elapsedInfluence) + elapsedRatio * elapsedInfluence,
      0.35,
      0.95,
    );

  const prudentSlots = rawSlots.map((slot) => {
    const hoursAhead = Math.max(0, (Date.parse(slot.startsAt) - now) / 3_600_000);
    const recovery = clamp(hoursAhead / 8, 0, 1);
    const factor = nearTermFactor + (farTermFactor - nearTermFactor) * recovery;
    return {
      startsAt: slot.startsAt,
      estimatedWh: Math.round(slot.estimatedWh * factor),
    };
  });

  const rawPlanningWh = rawSlots.reduce((sum, slot) => sum + slot.estimatedWh, 0);
  const prudentPlanningWh = prudentSlots.reduce((sum, slot) => sum + slot.estimatedWh, 0);
  const rawTodayWh = forecastTodayWh || alignedActualTodayWh + rawPlanningWh;
  const rawRemainingWh = forecastRemainingWh || rawPlanningWh;
  const todayRecoveryFactor = clamp(
    nearTermFactor + (farTermFactor - nearTermFactor) * 0.55,
    0.08,
    0.95,
  );
  const prudentRemainingWh = Math.round(rawRemainingWh * todayRecoveryFactor);
  const prudentTodayWh = Math.min(
    Math.round(rawTodayWh),
    Math.round(alignedActualTodayWh + prudentRemainingWh),
  );
  const correctionPercent = rawRemainingWh > 0
    ? Math.round((1 - prudentRemainingWh / rawRemainingWh) * 100)
    : 0;

  const hasTwoObservations = liveRatio !== null && elapsedRatio !== null;
  let confidence: SolarForecastConfidence = "low";
  if (rawSlots.length >= 12 && hasTwoObservations && dayProgress >= 0.15 && (cloudCover ?? 0) < 75) {
    confidence = "high";
  } else if (rawSlots.length >= 6 && (liveRatio !== null || elapsedRatio !== null) && (cloudCover ?? 0) < 85) {
    confidence = "medium";
  }

  // The card presents daily energy values, so the comparison must use the
  // cumulative production expected at the same time of day. Instantaneous
  // power remains only as a fallback when Forecast.Solar has not provided a
  // usable elapsed-energy value yet (typically around sunrise).
  const observedRatio = elapsedRatio ?? liveRatio;
  const observedGap = observedRatio === null
    ? null
    : Math.max(0, Math.round((1 - observedRatio) * 100));
  const explanation = observedGap === null
    ? "La prévision prudente applique les pertes habituelles de l’installation jusqu’à disposer de suffisamment de mesures réelles."
    : observedGap >= 10
      ? elapsedRatio !== null
        ? `${cloudCover !== null && cloudCover >= 85 ? "Ciel très couvert : " : ""}${formatEnergyKwh(alignedActualTodayWh)} kWh produits pour ${formatEnergyKwh(expectedElapsedWh)} kWh initialement prévus à cette heure (${observedGap} % de moins).`
        : `${cloudCover !== null && cloudCover >= 85 ? "Ciel très couvert : " : ""}${Math.round(actualSolarWatts)} W produits pour ${Math.round(forecastSolarWatts)} W attendus à cet instant (${observedGap} % de moins).`
      : null;

  return {
    rawSlots,
    prudentSlots,
    rawTodayWh: Math.round(rawTodayWh),
    prudentTodayWh,
    rawRemainingWh: Math.round(rawRemainingWh),
    prudentRemainingWh,
    correctionPercent,
    confidence,
    explanation,
  };
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
      explanation: "Activez la prévision solaire dans la box 1.2.3. Home, puis associez-la au tableau Énergie.",
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
  const confidence = input.forecastConfidence ??
    (slots.length >= 12 ? "high" : slots.length >= 5 ? "medium" : "low");
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

  if (batteryCanFundEarlyStart && afternoonCanRefill && confidence !== "low") {
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
