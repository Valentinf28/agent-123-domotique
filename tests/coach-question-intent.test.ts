import test from 'node:test';
import assert from 'node:assert/strict';
import { asksForBatteryEndurance, asksForCoachActionPlan, asksForCurrentWeekCost, asksForFiltrationBatteryProtection, asksForLastWeekCost, batteryChargeTargetPercent, coachQuestionIntent, needsDeterministicFinancialAnswer } from '../lib/coach-question-intent';

test('distingue économiser la batterie d’une économie financière', () => {
  assert.equal(coachQuestionIntent('Comment économiser ma batterie ce soir ?'), 'battery');
  assert.equal(needsDeterministicFinancialAnswer('Comment économiser ma batterie ce soir ?'), false);
  assert.equal(coachQuestionIntent('Comment préserver la réserve batterie ?'), 'battery');
  assert.equal(coachQuestionIntent('Comment préserver la batterie après le solaire ?'), 'battery');
});

test('reconnaît une demande de plan issue des deux semaines d’analyse', () => {
  assert.equal(asksForCoachActionPlan('Quel plan me proposes-tu après 14 jours ?'), true);
  assert.equal(asksForCoachActionPlan('Quelles sont les trois actions prioritaires à faire ?'), true);
  assert.equal(asksForCoachActionPlan('Allume la terrasse à 22 h'), false);
});

test('reconnaît les questions d’autonomie de la batterie', () => {
  assert.equal(asksForBatteryEndurance('La batterie va tenir toute la nuit ?'), true);
  assert.equal(asksForBatteryEndurance('Combien d’heures d’autonomie reste-t-il à la batterie ?'), true);
  assert.equal(asksForBatteryEndurance('Comment économiser ma batterie ?'), false);
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

test('classe le gain solaire comme financier et la recharge au surplus comme véhicule', () => {
  assert.equal(coachQuestionIntent('Combien puis-je gagner en déplaçant mes usages vers le solaire ?'), 'money');
  assert.equal(coachQuestionIntent('Crée une règle pour charger la voiture uniquement avec le surplus solaire'), 'vehicle');
});

test('reconnaît le scénario filtration qui vide la batterie sans solaire', () => {
  assert.equal(asksForFiltrationBatteryProtection("La batterie a fait un appoint réseau à 15 %, la filtration aurait dû s'arrêter car la production solaire est insuffisante et le temps est pourri"), true);
  assert.equal(asksForFiltrationBatteryProtection('Combien consomme la filtration ?'), false);
});

test('reconnaît le coût demandé depuis le début de la semaine', () => {
  assert.equal(asksForCurrentWeekCost('Combien ai-je dépensé depuis le début de la semaine ?'), true);
  assert.equal(asksForCurrentWeekCost('Quel montant ai-je dépensé cette semaine ?'), true);
  assert.equal(asksForCurrentWeekCost("Combien ai-je dépensé aujourd'hui ?"), false);
});

test('reconnaît le coût demandé pour la semaine dernière', () => {
  assert.equal(asksForLastWeekCost('Combien ai-je dépensé la semaine dernière ?'), true);
  assert.equal(asksForLastWeekCost('Quel montant ai-je dépensé la semaine passée ?'), true);
  assert.equal(asksForLastWeekCost('Combien ai-je dépensé cette semaine ?'), false);
});

test('extrait entièrement le niveau de batterie demandé', () => {
  assert.equal(batteryChargeTargetPercent('À quelle heure la batterie sera à 95% ?'), 95);
  assert.equal(batteryChargeTargetPercent('Quand ma batterie atteindra 100 % ?'), 100);
  assert.equal(batteryChargeTargetPercent('La batterie est à 43 %'), null);
});
