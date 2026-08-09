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

test('explique un fonctionnement après le coucher sans inventer la consigne', () => {
  const reply = poolHeatPumpCoachReply('Pourquoi la PAC piscine a continué après le coucher du soleil ?');
  assert.ok(reply);
  assert.match(reply.answer, /ne permettent pas d’identifier rétrospectivement la cause/i);
  assert.doesNotMatch(reply.answer, /Vous indiquez[^.]*déjà à sa consigne/i);
  assert.equal(reply.automationProposal?.trigger, 'Au coucher du soleil');
});

test('refuse de figer la météo de demain dans une règle répétée', () => {
  const reply = poolHeatPumpCoachReply('Programme la PAC piscine demain à 14h car il fera beau');
  assert.ok(reply);
  assert.match(reply.answer, /ne transforme pas la météo ponctuelle/i);
  assert.equal(reply.automationProposal, null);
});

test('ne confond jamais filtration et PAC piscine', () => {
  assert.equal(poolHeatPumpCoachReply("La filtration a tourné après le solaire et vidé la batterie."), null);
});
