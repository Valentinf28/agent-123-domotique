import test from 'node:test';
import assert from 'node:assert/strict';
import { batteryProtectionGuidance, batterySavingsGuidance, filtrationBatteryProtectionGuidance, financialCoachGuidance, observedPeriodLabel, solarAutoconsumptionGuidance, solarCoachGuidance, unavailableEquipmentGuidance, vehicleChargingGuidance } from '../lib/coach-local-advice';

test('annonce exactement la période réellement observée', () => {
  assert.equal(observedPeriodLabel(1), 'Sur la journée disponible');
  assert.equal(observedPeriodLabel(12), 'Sur les 12 derniers jours disponibles');
});

test('ne présente pas zéro comme une prévision solaire absente', () => {
  const answer = solarCoachGuidance({
    forecastAvailable: false,
    exportWatts: 0,
    prudentRemainingKwh: '0 kWh',
  });
  assert.match(answer, /aucune prévision solaire exploitable/i);
  assert.doesNotMatch(answer, /estime encore 0 kWh/i);
  assert.match(answer, /ne propose donc pas de créneau futur/i);
});

test('utilise la prévision prudente uniquement lorsqu’elle existe', () => {
  const answer = solarCoachGuidance({
    forecastAvailable: true,
    exportWatts: 850,
    prudentRemainingKwh: '4,2 kWh',
  });
  assert.match(answer, /850 W/);
  assert.match(answer, /4,2 kWh/);
  assert.match(answer, /garde-fous/);
});

test('transforme le surplus historique en priorités limitées aux appareils configurés', () => {
  const answer = solarAutoconsumptionGuidance({
    observedDays: 12,
    exportedWh: 136_300,
    peakHour: 15,
    flexibleLoads: [
      { label: 'PAC piscine', category: 'pool_heat_pump' },
      { label: 'Borne Lektrico', category: 'vehicle' },
    ],
    currentExportWatts: 0,
  });
  assert.match(answer, /136,3 kWh/);
  assert.match(answer, /11,4 kWh par jour/);
  assert.match(answer, /PAC piscine, Borne Lektrico/);
  assert.match(answer, /aucun démarrage immédiat/i);
  assert.doesNotMatch(answer, /chauffe-eau/i);
});

test('date correctement le créneau de recharge et refuse de confondre aujourd’hui avec demain', () => {
  const answer = vehicleChargingGuidance({
    now: new Date('2026-08-09T00:30:00+02:00'),
    vehicleWatts: 0,
    currentExportWatts: 0,
    forecastSlots: [
      { startsAt: '2026-08-09T12:00:00+02:00', estimatedWh: 3200 },
      { startsAt: '2026-08-10T12:00:00+02:00', estimatedWh: 4100 },
    ],
    forecastConfidence: 'low',
    reservePercent: 20,
    offPeakPeriods: [{ start: '00:00', end: '08:00' }],
  });
  assert.match(answer, /demain vers 12:00/);
  assert.match(answer, /confiance est faible/i);
  assert.match(answer, /attendez que le surplus soit réellement mesuré/i);
  assert.match(answer, /00:00–08:00/);
  assert.match(answer, /20 %/);

  const today = vehicleChargingGuidance({
    now: new Date('2026-08-09T00:30:00+02:00'),
    vehicleWatts: 0,
    currentExportWatts: 0,
    forecastSlots: [{ startsAt: '2026-08-09T12:00:00+02:00', estimatedWh: 3200 }],
    forecastConfidence: 'medium',
    reservePercent: 20,
    offPeakPeriods: [],
  });
  assert.match(today, /aujourd’hui vers 12:00/);
  assert.doesNotMatch(today, /demain/);
});

test('conseille immédiatement la recharge seulement sur un surplus réellement mesuré', () => {
  const answer = vehicleChargingGuidance({
    now: new Date('2026-08-09T12:00:00+02:00'),
    vehicleWatts: 0,
    currentExportWatts: 1800,
    forecastSlots: [],
    forecastConfidence: 'low',
    reservePercent: 20,
    offPeakPeriods: [],
  });
  assert.match(answer, /1[  ]800 W sont actuellement injectés/);
  assert.match(answer, /démarrez progressivement/i);
});

test('n’invente pas le gain financier de la batterie', () => {
  const answer = batterySavingsGuidance(false);
  assert.match(answer, /prix du kWh n’est pas renseigné/i);
  assert.match(answer, /ne peut pas être converti honnêtement en euros/i);
  assert.match(answer, /protéger la réserve/i);
});

test('répond à la protection après le solaire sans répéter le bilan de surplus', () => {
  const answer = batteryProtectionGuidance({
    batteryPercent: 62,
    reservePercent: 15,
    solarWatts: 0,
    batteryWatts: 820,
    flexibleLoads: ['PAC piscine', 'Filtration piscine'],
  });
  assert.match(answer, /solaire est terminé/i);
  assert.match(answer, /batterie est à 62 %/i);
  assert.match(answer, /réserve configurée à 15 %/i);
  assert.match(answer, /PAC piscine, Filtration piscine/i);
  assert.doesNotMatch(answer, /kWh ont été injectés|autour de 15 h/i);
});

test('propose un vrai garde-fou pour la filtration quand la batterie atteint sa réserve', () => {
  const answer = filtrationBatteryProtectionGuidance({
    reservePercent: 15,
    filtrationWatts: 684,
    configuredForEnergyControl: false,
  });
  assert.match(answer, /réserve de 15 %/i);
  assert.match(answer, /684 W/);
  assert.match(answer, /à 20 %, mettre la filtration en pause/i);
  assert.match(answer, /surplus réel suffit/i);
  assert.match(answer, /durée quotidienne nécessaire/i);
  assert.match(answer, /usage flexible pilotable/i);
  assert.doesNotMatch(answer, /73,3 kWh|209,1 kWh/);
});

test('projette uniquement les achats réseau et déduit la vente du surplus', () => {
  const answer = financialCoachGuidance({
    observedDays: 10,
    importedWh: 50_000,
    exportedWh: 20_000,
    importCostEuros: 12,
    exportRevenueEuros: 2,
    netEnergyCostEuros: 10,
    peakImportedWh: 30_000,
    offPeakImportedWh: 20_000,
    shiftableToSolarWh: 20_000,
    shiftableSavingsEuros: 3,
    plan: 'base',
    tariffGuidance: 'Option Base configurée.',
  });
  assert.match(answer, /acheté 50 kWh au réseau/i);
  assert.match(answer, /injecté 20 kWh/i);
  assert.match(answer, /30\s*€/);
  assert.match(answer, /6\s*€ de rémunération/i);
  assert.match(answer, /60 kWh d’achats en journée/i);
  assert.match(answer, /9\s*€ par mois/i);
  assert.match(answer, /flux réseau mesurés/i);
});

test('ne déduit pas une injection dont le tarif de rachat manque', () => {
  const answer = financialCoachGuidance({
    observedDays: 10,
    importedWh: 50_000,
    exportedWh: 20_000,
    importCostEuros: 12,
    exportRevenueEuros: null,
    netEnergyCostEuros: null,
    peakImportedWh: 30_000,
    offPeakImportedWh: 20_000,
    shiftableToSolarWh: 20_000,
    shiftableSavingsEuros: null,
    plan: 'hp_hc',
    tariffGuidance: 'Tarif HP/HC configuré.',
  });
  assert.match(answer, /36\s*€/);
  assert.match(answer, /tarif de rachat n’est pas renseigné/i);
  assert.match(answer, /n’est pas déduite/i);
});

test('refuse tout montant si le prix d’achat manque', () => {
  const answer = financialCoachGuidance({
    observedDays: 5,
    importedWh: 12_000,
    exportedWh: 0,
    importCostEuros: null,
    exportRevenueEuros: 0,
    netEnergyCostEuros: null,
    peakImportedWh: 12_000,
    offPeakImportedWh: 0,
    shiftableToSolarWh: 0,
    shiftableSavingsEuros: null,
    plan: 'base',
    tariffGuidance: 'Prix manquant.',
  });
  assert.match(answer, /ne fabrique donc aucun montant/i);
  assert.doesNotMatch(answer, /environ \d+\s*€/i);
});

test('refuse de parler comme si une borne ou un chauffe-eau absent existait', () => {
  const missing = { vehicle: false, hotWater: false };
  assert.match(unavailableEquipmentGuidance('vehicle', missing) || '', /aucune borne ni voiture/i);
  assert.match(unavailableEquipmentGuidance('hot-water', missing) || '', /aucun chauffe-eau pilotable/i);
  assert.equal(unavailableEquipmentGuidance('vehicle', { ...missing, vehicle: true }), null);
});
