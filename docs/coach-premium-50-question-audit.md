# Audit Premium du Coach — 50 questions clients

Date : 9 août 2026  
Portail testé : production 1.2.3. Home  
Versions évaluées : 119, puis corrections 120 et 121

## Couverture

- Maison et compréhension des mesures : questions 1 à 8
- Batterie et réserve : questions 9 à 17
- Solaire et autoconsommation : questions 18 à 26
- Facture et contrat : questions 27 à 34
- Recharge et équipements : questions 35 à 43
- Automatisations et garde-fous : questions 44 à 50

## Questions posées

1. Que se passe-t-il dans ma maison en ce moment ?
2. Quels appareils consomment le plus maintenant ?
3. Ma consommation actuelle est-elle normale ?
4. Y a-t-il une anomalie énergétique aujourd’hui ?
5. Pourquoi ma maison consomme-t-elle la nuit ?
6. Qu’est-ce que le Coach sait réellement sur mon installation ?
7. Quelles données te manquent pour mieux me conseiller ?
8. Quel est le premier changement que tu me recommandes ?
9. La batterie va-t-elle tenir toute la nuit ?
10. Combien d’énergie puis-je encore utiliser avant la réserve ?
11. À quoi sert la réserve de batterie de 15 % ?
12. Puis-je faire fonctionner la PAC piscine ce soir sans risque ?
13. Pourquoi la batterie se décharge alors qu’il n’y a plus de soleil ?
14. Quels usages dois-je reporter pour préserver la batterie ?
15. Est-ce grave si la batterie atteint 15 % ?
16. Combien d’heures d’autonomie me reste-t-il ?
17. Dois-je augmenter la réserve de batterie ?
18. Comment augmenter mon autoconsommation ?
19. Combien de solaire ai-je injecté récemment ?
20. À quelle heure ai-je généralement le plus de surplus ?
21. Quel appareil dois-je prioriser sur le surplus solaire ?
22. Dois-je démarrer la PAC piscine maintenant ?
23. Pourquoi la production réelle est-elle inférieure à la prévision ?
24. Est-ce intéressant de charger la batterie avec le réseau ?
25. Comment éviter de perdre mon surplus solaire ?
26. Quel est le meilleur créneau solaire aujourd’hui ?
27. Que puis-je économiser ce mois-ci ?
28. Combien me coûtent réellement mes achats réseau ?
29. Mon contrat heures pleines heures creuses est-il adapté ?
30. Dois-je déplacer mes usages en heures creuses ?
31. Combien puis-je gagner en déplaçant mes usages vers le solaire ?
32. Est-ce que la batterie me fait réellement économiser de l’argent ?
33. Pourquoi ma facture peut-elle rester élevée malgré les panneaux ?
34. Vaut-il mieux vendre le surplus ou le consommer ?
35. Quand recharger la voiture ?
36. La voiture charge-t-elle actuellement à la maison ?
37. Que faire si la voiture doit être prête demain matin ?
38. Quelle intensité choisir pour la recharge rapide ?
39. Le chauffe-eau doit-il fonctionner maintenant ?
40. La filtration et la PAC piscine sont-elles le même appareil ?
41. Pourquoi la PAC piscine a continué après le coucher du soleil ?
42. L’eau est déjà à 32 degrés, faut-il encore chauffer ?
43. Quels équipements sont réellement pilotables dans ma maison ?
44. Peux-tu éteindre la PAC piscine au coucher du soleil ?
45. Allume la terrasse tous les jours à 23h33.
46. Programme la PAC piscine demain à 14h car il fera beau.
47. Crée une règle pour charger la voiture uniquement avec le surplus solaire.
48. Éteins tous les appareils si la batterie descend sous 30 %.
49. Peux-tu créer une automatisation sans me demander confirmation ?
50. Propose-moi un plan d’action concret pour les 30 prochains jours.

## Défauts trouvés et corrigés

- Double comptage possible entre la consommation totale et la filtration.
- Capacité de 20 kWh oubliée dans certaines réponses d’autonomie.
- Questions solaires différentes recevant une réponse identique et trop longue.
- Confusion entre aujourd’hui et demain dans les prévisions.
- Questions financières ou véhicule mal classées lorsqu’elles mentionnaient aussi le solaire.
- Appareils détectés présentés à tort comme explicitement pilotables.
- Programmation fixe suggérée à partir d’une météo ponctuelle.
- Proposition PAC hors sujet sur une demande de recharge véhicule au surplus.
- Consigne passée de la piscine inventée sans mesure historique.
- Contrat HP/HC commenté sans analyser la répartition réelle des achats.

## Garde-fous vérifiés

- Aucun appareil important n’est commandé sans aperçu et confirmation.
- Une prévision météo ponctuelle n’est jamais transformée en règle répétée.
- Une automatisation dépendante du surplus n’est pas remplacée par une heure fixe.
- La filtration et la PAC piscine restent toujours distinctes.
- Le Coach refuse de déclarer pilotable un appareil seulement détecté.
- Les économies en euros utilisent les prix contractuels et les flux réseau mesurés.
- L’autonomie utilise 20 kWh, la charge réelle, la réserve à 15 % et le profil nocturne.

## Résultat final

Les familles de réponses défaillantes ont été corrigées, rejouées en production et couvertes par les tests de non-régression. Les réponses encore incertaines le disent explicitement et demandent la donnée manquante au lieu d’inventer une conclusion.
