import test from 'node:test';
import assert from 'node:assert/strict';
import { batterySavingsGuidance, financialCoachGuidance, observedPeriodLabel, solarAutoconsumptionGuidance, solarCoachGuidance, unavailableEquipmentGuidance } from '../lib/coach-local-advice';

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

test('n’invente pas le gain financier de la batterie', () => {
  const answer = batterySavingsGuidance(false);
  assert.match(answer, /prix du kWh n’est pas renseigné/i);
  assert.match(answer, /ne peut pas être converti honnêtement en euros/i);
  assert.match(answer, /protéger la réserve/i);
});

test('projette uniquement les achats réseau et déduit la vente du surplus', () => {
  const answer = financialCoachGuidance({
    observedDays: 10,
    importedWh: 50_000,
    exportedWh: 20_000,
    importCostEuros: 12,
    exportRevenueEuros: 2,
    netEnergyCostEuros: 10,
    plan: 'base',
    tariffGuidance: 'Option Base configurée.',
  });
  assert.match(answer, /acheté 50 kWh au réseau/i);
  assert.match(answer, /injecté 20 kWh/i);
  assert.match(answer, /30\s*€/);
  assert.match(answer, /6\s*€ de rémunération/i);
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
