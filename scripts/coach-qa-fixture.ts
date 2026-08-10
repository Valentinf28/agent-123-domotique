const now = new Date();
const at = (hours: number) => new Date(now.getTime() + hours * 3_600_000).toISOString();

export const coachHouseFixture = {
  dossier: { id: 1, publicId: "DOSSIER-PILOTE", name: "Maison pilote", batteryCapacityWh: 20_000, batteryReservePercent: 15 },
  tariff: {
    plan: "hp_hc",
    offPeakPeriods: [{ start: "00:00", end: "08:00" }],
    prices: { baseMilliEurosPerKwh: null, peakMilliEurosPerKwh: 175, offPeakMilliEurosPerKwh: 139, exportMilliEurosPerKwh: 100 },
    pricesConfigured: true,
  },
  equipmentCapabilities: { vehicle: true, hotWater: true },
  current: {
    solarWatts: 2_400, homeWatts: 1_700, gridWatts: -700, batteryPercent: 78, batteryWatts: -350,
    filtrationWatts: 692, hotWaterWatts: 0, vehicleWatts: 0, dailyProductionWh: 24_600, dailyConsumptionWh: 19_200,
  },
  historySamples: 2_402,
  week: { observedDays: 13, importedWh: 6_200, exportedWh: 136_300 },
  gridCost: {
    importedWh: 6_200, exportedWh: 136_300, peakImportedWh: 4_000, offPeakImportedWh: 2_200,
    importCostEuros: 1.01, exportRevenueEuros: 13.63, netEnergyCostEuros: -12.62,
    projectedMonthlyImportWh: 14_300, projectedMonthlyExportWh: 314_500,
    projectedMonthlyImportCostEuros: 2.33, projectedMonthlyExportRevenueEuros: 31.45,
    projectedMonthlyNetEnergyCostEuros: -29.12, shiftableMonthlyImportWh: 11_100, maxMonthlySavingsEuros: 1.94,
  },
  gridCosts: {
    today: { importedWh: 800, exportedWh: 12_000, importCostEuros: 0.13, exportRevenueEuros: 1.2, observedDays: 1 },
    week: { importedWh: 3_100, exportedWh: 70_000, importCostEuros: 0.51, exportRevenueEuros: 7, observedDays: 7 },
    lastWeek: { importedWh: 3_400, exportedWh: 72_000, importCostEuros: 0.56, exportRevenueEuros: 7.2, observedDays: 7 },
    last7: { importedWh: 3_500, exportedWh: 75_000, importCostEuros: 0.58, exportRevenueEuros: 7.5, observedDays: 7 },
    month: { importedWh: 6_200, exportedWh: 136_300, importCostEuros: 1.01, exportRevenueEuros: 13.63, observedDays: 13 },
  },
  vehicleEnergyToday: { available: true, energyWh: 7_400, sampleCount: 84, coveredMinutes: 315 },
  vehicleEnergyYesterday: { available: true, energyWh: 9_200, sampleCount: 120, coveredMinutes: 540 },
  filtrationEnergyToday: { available: true, energyWh: 4_200, sampleCount: 96, coveredMinutes: 365 },
  actionPlan: {
    status: "ready", learningDays: 14, daysRemaining: 0,
    actions: [
      { priority: 1, title: "Décaler la filtration", impact: "moins d’achat réseau" },
      { priority: 2, title: "Recharger au surplus", impact: "plus d’autoconsommation" },
      { priority: 3, title: "Préserver la batterie", impact: "réserve respectée" },
    ],
  },
  batteryOutlook: {
    available: true, usableWh: 12_600, expectedWh: 5_900, marginWh: 6_700, holdsUntilSolar: true,
    nextSolarAt: at(8), horizonHours: 8, confidence: "measured", observedNights: 12,
  },
  solarForecast: {
    available: true, source: "Prévision météo locale", confidence: "medium", prudentRemainingWh: 18_000,
    slots: [{ startsAt: at(12), estimatedWh: 3_200 }, { startsAt: at(13), estimatedWh: 3_800 }],
    rawSlots: [], rawTodayWh: 30_000, prudentTodayWh: 25_000, rawRemainingWh: 20_000,
    correctionPercent: 83, explanation: "prévision corrigée",
  },
  predictivePlan: null,
  predictivePlans: [
    { loadId: "filtration", loadLabel: "Filtration piscine", loadCategory: "pool", powerWatts: 692 },
    { loadId: "pac", loadLabel: "PAC piscine", loadCategory: "pool", powerWatts: 2_000 },
    { loadId: "vehicle", loadLabel: "Borne véhicule", loadCategory: "vehicle", powerWatts: 7_400 },
  ],
  consumptionBreakdown: [
    { id: "filtration", name: "Filtration piscine", watts: 692, sharePercent: 41 },
    { id: "other-home", name: "Autres usages", watts: 1_008, sharePercent: 59 },
  ],
  insights: [
    { id: "historical-solar-export", goal: "solar", title: "Surplus solaire", description: "136,3 kWh injectés, le plus souvent vers 15 h", impact: "Plus d’autoconsommation", action: "Décaler les usages" },
    { id: "battery-protection", goal: "battery", title: "Préserver la batterie", description: "Les usages flexibles sollicitent la batterie", impact: "Réserve protégée", action: "Reporter les usages" },
    { id: "vehicle-charge", goal: "money", title: "Recharge véhicule", description: "La borne peut suivre le surplus", impact: "Achats évités", action: "Utiliser le mode Surplus" },
  ],
} as any;
