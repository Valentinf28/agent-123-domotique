import test from 'node:test';
import assert from 'node:assert/strict';
import { poolHeatPumpCoachReply } from '../lib/pool-heat-pump-coach';

test('reprend précisément le constat PAC fourni par le client', () => {
  const reply = poolHeatPumpCoachReply("La PAC de la piscine a tourné jusqu’à 21h alors qu’il n’y avait plus de production solaire, ça a vidé la batterie. L’eau était à 32 °C, ça ne servait à rien. Comment améliorer ça ?");
  assert.match(reply?.answer || '', /vous indiquez que l’eau était déjà à 32 °C/i);
  assert.match(reply?.answer || '', /d’après votre constat/i);
  assert.equal(reply?.automationProposal?.trigger, 'Au coucher du soleil');
  assert.equal(reply?.automationProposal?.action, 'Éteindre la PAC piscine');
});

test('ne fabrique pas une température absente du message', () => {
  const reply = poolHeatPumpCoachReply("La PAC a continué après l’arrêt de la production solaire et a vidé la batterie. Ça ne servait à rien.");
  assert.ok(reply);
  assert.doesNotMatch(reply?.answer || '', /32\s*°/);
  assert.match(reply?.answer || '', /vous indiquez/i);
});

test('ne transforme pas une simple question batterie en scénario inventé', () => {
  assert.equal(poolHeatPumpCoachReply("Est-ce que la PAC peut utiliser la batterie demain ?"), null);
});

test('ne confond jamais filtration et PAC piscine', () => {
  assert.equal(poolHeatPumpCoachReply("La filtration a tourné après le solaire et vidé la batterie."), null);
});
