import type { OffPeakPeriod, TariffPrices } from "./energy-insights";

type GridSample = { capturedAt: string; gridWatts: number };

function parisMinutes(date: Date) {
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  return hour * 60 + minute;
}

function inPeriod(minutes: number, period: OffPeakPeriod) {
  const toMinutes = (value: string) => {
    const [hour, minute] = value.split(":").map(Number);
    return hour * 60 + minute;
  };
  const start = toMinutes(period.start);
  const end = toMinutes(period.end);
  return start < end
    ? minutes >= start && minutes < end
    : minutes >= start || minutes < end;
}

export function measuredGridCost(input: {
  samples: GridSample[];
  plan: "base" | "hp_hc";
  periods: OffPeakPeriod[];
  prices: TariffPrices;
}) {
  const samples = [...input.samples].sort((left, right) =>
    Date.parse(left.capturedAt) - Date.parse(right.capturedAt));
  let importedWh = 0;
  let exportedWh = 0;
  let importCostEuros = 0;
  let exportRevenueEuros = 0;
  let importPriceComplete = true;
  let exportPriceComplete = input.prices.exportMilliEurosPerKwh != null;

  samples.forEach((sample, index) => {
    const next = samples[index + 1];
    if (!next) return;
    const elapsedHours = Math.min(15 * 60_000, Math.max(0,
      Date.parse(next.capturedAt) - Date.parse(sample.capturedAt))) / 3_600_000;
    const imported = Math.max(0, sample.gridWatts) * elapsedHours;
    const exported = Math.max(0, -sample.gridWatts) * elapsedHours;
    importedWh += imported;
    exportedWh += exported;
    const importPrice = input.plan === "base"
      ? input.prices.baseMilliEurosPerKwh
      : input.periods.some((period) => inPeriod(parisMinutes(new Date(sample.capturedAt)), period))
        ? input.prices.offPeakMilliEurosPerKwh
        : input.prices.peakMilliEurosPerKwh;
    if (imported > 0 && importPrice == null) importPriceComplete = false;
    if (importPrice != null) importCostEuros += imported / 1000 * importPrice / 1000;
    if (exported > 0 && input.prices.exportMilliEurosPerKwh == null) exportPriceComplete = false;
    if (input.prices.exportMilliEurosPerKwh != null) {
      exportRevenueEuros += exported / 1000 * input.prices.exportMilliEurosPerKwh / 1000;
    }
  });

  return {
    importedWh,
    exportedWh,
    importCostEuros: importPriceComplete ? importCostEuros : null,
    exportRevenueEuros: exportPriceComplete ? exportRevenueEuros : null,
    netEnergyCostEuros: importPriceComplete && (exportedWh === 0 || exportPriceComplete)
      ? importCostEuros - exportRevenueEuros
      : null,
  };
}
