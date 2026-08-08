import test from 'node:test';
import assert from 'node:assert/strict';
import { batterySavingsGuidance, observedPeriodLabel, solarCoachGuidance, unavailableEquipmentGuidance } from '../lib/coach-local-advice';

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

test('n’invente pas le gain financier de la batterie', () => {
  const answer = batterySavingsGuidance(false);
  assert.match(answer, /prix du kWh n’est pas renseigné/i);
  assert.match(answer, /ne peut pas être converti honnêtement en euros/i);
  assert.match(answer, /protéger la réserve/i);
});

test('refuse de parler comme si une borne ou un chauffe-eau absent existait', () => {
  const missing = { vehicle: false, hotWater: false };
  assert.match(unavailableEquipmentGuidance('vehicle', missing) || '', /aucune borne ni voiture/i);
  assert.match(unavailableEquipmentGuidance('hot-water', missing) || '', /aucun chauffe-eau pilotable/i);
  assert.equal(unavailableEquipmentGuidance('vehicle', { ...missing, vehicle: true }), null);
});
