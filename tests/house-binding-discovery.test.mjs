import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeHouseBindings } from '../shared/house-binding-discovery.js';

const profile = {
  solarPower: ['sensor.onduleur_pv_power', 'production solaire'],
  homePower: ['sensor.maison_power', 'consommation maison'],
  gridPower: ['sensor.reseau_power', 'puissance reseau'],
};

test('reconnaît automatiquement les identifiants exacts des capteurs essentiels', () => {
  const report = analyzeHouseBindings({
    profile,
    essentialKeys: Object.keys(profile),
    inventory: [
      { entityId: 'sensor.onduleur_pv_power', name: 'Onduleur', state: '3200' },
      { entityId: 'sensor.maison_power', name: 'Maison', state: '850' },
      { entityId: 'sensor.reseau_power', name: 'Réseau', state: '-1200' },
    ],
  });
  assert.equal(report.ready, true);
  assert.deepEqual(report.bindings, {
    solarPower: 'sensor.onduleur_pv_power',
    homePower: 'sensor.maison_power',
    gridPower: 'sensor.reseau_power',
  });
});

test('ne choisit pas seul entre deux correspondances ambiguës', () => {
  const report = analyzeHouseBindings({
    profile: { solarPower: ['production solaire'] },
    essentialKeys: ['solarPower'],
    inventory: [
      { entityId: 'sensor.pv_est', name: 'Production solaire est', state: '1200' },
      { entityId: 'sensor.pv_sud', name: 'Production solaire sud', state: '2200' },
    ],
  });
  assert.equal(report.ready, false);
  assert.equal(report.resolved.length, 0);
  assert.equal(report.ambiguous.length, 1);
});

test('écarte les entités de démonstration pour une maison client', () => {
  const report = analyzeHouseBindings({
    profile: { solarPower: ['input_number.demo_solar_power', 'production solaire'] },
    essentialKeys: ['solarPower'],
    inventory: [{ entityId: 'input_number.demo_solar_power', name: 'Production showroom', state: '4500' }],
  });
  assert.equal(report.missing.length, 1);
  assert.equal(report.bindings.solarPower, undefined);
});

test('conserve le choix manuel du technicien même si le capteur est temporairement indisponible', () => {
  const report = analyzeHouseBindings({
    profile: { homePower: ['consommation maison'] },
    essentialKeys: ['homePower'],
    overrides: { homePower: 'sensor.compteur_tableau' },
    inventory: [{ entityId: 'sensor.compteur_tableau', name: 'Compteur tableau', state: 'unavailable' }],
  });
  assert.equal(report.ready, true);
  assert.equal(report.bindings.homePower, 'sensor.compteur_tableau');
  assert.equal(report.resolved[0].source, 'manual');
});
