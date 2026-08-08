import test from 'node:test';
import assert from 'node:assert/strict';
import { coachQuestionIntent, needsDeterministicFinancialAnswer } from '../lib/coach-question-intent';

test('distingue économiser la batterie d’une économie financière', () => {
  assert.equal(coachQuestionIntent('Comment économiser ma batterie ce soir ?'), 'battery');
  assert.equal(needsDeterministicFinancialAnswer('Comment économiser ma batterie ce soir ?'), false);
  assert.equal(coachQuestionIntent('Comment préserver la réserve batterie ?'), 'battery');
});

test('reconnaît les demandes liées à la facture et au contrat', () => {
  assert.equal(coachQuestionIntent('Comment réduire ma facture avec mon tarif actuel ?'), 'money');
  assert.equal(coachQuestionIntent('Que puis-je économiser ce mois-ci ?'), 'money');
  assert.equal(coachQuestionIntent('Quelles sont mes heures creuses ?'), 'money');
  assert.equal(coachQuestionIntent('Combien la batterie me fait-elle économiser sur ma facture ?'), 'money');
});

test('ne détourne pas une demande solaire ou de recharge vers le bilan financier', () => {
  assert.equal(coachQuestionIntent('Comment économiser grâce à mon surplus solaire ?'), 'solar');
  assert.equal(coachQuestionIntent('Quand recharger ma voiture demain ?'), 'vehicle');
  assert.equal(coachQuestionIntent('Comment piloter mon ballon d’eau chaude ?'), 'hot-water');
});
