import assert from 'node:assert/strict';
import test from 'node:test';
import {
  analyzeProvisioning,
  applyCertainProvisioning,
  entityIsShowroomOnly,
} from '../shared/provisioning-discovery.js';

const shelly = {
  id: 'shelly-pro-1pm', catalogId: 'shelly-pro-1pm', brand: 'Shelly', model: 'Pro 1PM',
  category: 'Eau chaude', room: 'Local technique', status: 'Prêt',
};

test('associe automatiquement un appareil uniquement lorsque le résultat est distinct et certain', () => {
  const report = analyzeProvisioning({
    items: [shelly],
    inventory: [
      { entityId: 'switch.shelly_pro_1pm_chauffe_eau', name: 'Shelly Pro 1PM chauffe-eau', domain: 'switch', state: 'off' },
      { entityId: 'sensor.temperature_exterieure', name: 'Température extérieure', domain: 'sensor', state: '22' },
    ],
  });
  assert.equal(report.certain.length, 1);
  assert.equal(report.certain[0].entityId, 'switch.shelly_pro_1pm_chauffe_eau');
  assert.equal(report.ambiguous.length, 0);
});
test('exige une confirmation quand plusieurs entités obtiennent des scores proches', () => {
  const report = analyzeProvisioning({
    items: [shelly],
    inventory: [
      { entityId: 'switch.shelly_pro_1pm_a', name: 'Shelly Pro 1PM A', domain: 'switch', state: 'off' },
      { entityId: 'switch.shelly_pro_1pm_b', name: 'Shelly Pro 1PM B', domain: 'switch', state: 'on' },
    ],
  });
  assert.equal(report.certain.length, 0);
  assert.equal(report.ambiguous.length, 1);
  assert.equal(report.ambiguous[0].requiresConfirmation, true);
  assert.equal(report.ambiguous[0].candidates.length, 2);
});

test('ne mélange jamais les entités de démonstration avec une maison cliente', () => {
  const demo = { entityId: 'input_boolean.demo_heating', name: 'Chauffage showroom', domain: 'input_boolean', state: 'on' };
  assert.equal(entityIsShowroomOnly(demo), true);
  const report = analyzeProvisioning({
    items: [{ ...shelly, brand: 'Demo', model: 'Heating', category: 'Chauffage' }],
    inventory: [demo],
    isShowroom: false,
  });
  assert.equal(report.certain.length, 0);
  assert.equal(report.missing.length, 1);
});

test('préserve les associations du technicien et applique les suggestions de façon idempotente', () => {
  const manual = {
    ...shelly, catalogId: 'manuel', matchedEntityId: 'switch.choix_technicien',
    matchedEntityName: 'Choix technicien', status: 'Testé',
  };
  const report = analyzeProvisioning({
    items: [manual, shelly],
    inventory: [
      { entityId: 'switch.choix_technicien', name: 'Choix technicien', domain: 'switch', state: 'on' },
      { entityId: 'switch.shelly_pro_1pm_chauffe_eau', name: 'Shelly Pro 1PM chauffe-eau', domain: 'switch', state: 'off' },
    ],
  });
  assert.equal(report.preserved.length, 1);
  const once = applyCertainProvisioning([manual, shelly], report);
  const twice = applyCertainProvisioning(once, report);
  assert.deepEqual(twice, once);
  assert.equal(twice[0].matchedEntityId, 'switch.choix_technicien');
  assert.equal(twice[0].status, 'Testé');
});

test('produit un rapport explicite pour les appareils manquants', () => {
  const report = analyzeProvisioning({ items: [shelly], inventory: [] });
  assert.deepEqual(report.missing.map((item) => item.key), ['shelly-pro-1pm:Local technique']);
});
