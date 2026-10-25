# La Box · Récupération 0.1.1 (qualification pilote)

Cette application séparée démarre avant l’agent principal et ne dépend ni de
Home Assistant Core, ni de son interface, ni du relais principal. Elle n’ouvre
aucun port réseau. Une connexion HTTPS sortante vers le portail officiel suffit.
Aucune dépendance Tailscale et aucune clé d’accès globale commune aux clients.

## Autorité

L’agent rattaché crée une clé de récupération distincte ; seul son hachage est
conservé au portail. La clé est liée à l’association exacte box/maison/propriétaire.
Un transfert, remplacement, retrait ou rotation de l’identité principale invalide
les anciens accès. Le secret n’est pas montré dans les interfaces client ou SAV.
Chaque action exige un ticket SAV autorisé, une session opérateur active et une
vérification juste avant l’exécution. Le diagnostic utilise le droit diagnostic ;
le redémarrage et la réparation exigent le nouveau droit explicite « secours logiciel ».
Les anciennes autorisations ne gagnent jamais ce droit automatiquement.

## Périmètre

- Lire un diagnostic minimal : version et état du logiciel, Core et service système.
- Démarrer/redémarrer uniquement l’agent officiel du même dépôt que le secours.
- Installer uniquement une version stable approuvée, égale au catalogue natif,
  après lecture intégrale et validation d’une sauvegarde locale complète incluant
  la configuration, la base de données et l’agent. Aucune suppression automatique.

Pas de shell, tunnel, proxy HA, commande physique, modification du réseau,
restauration, modification HAOS ou du démarrage système, ni action sur un autre module.
Le rôle Supervisor manager est nécessaire à la seule gestion de l’agent ; la liste
fermée des appels est appliquée dans le transport. L’application n’a ni accès hôte,
ni dossiers partagés, ni API Home Assistant, ni port entrant.

## Incertitudes et concurrence

Le service refuse une action si une tâche système native est en cours. Il ne consulte
pas le verrou de maintenance de l’agent en panne. L’intention est sauvegardée avec
fsync avant tout envoi ; après perte de réponse, seule l’observation reprend.
Aucun rejeu automatique après redémarrage ou retour Internet. Une opération non
confirmée reste visible ; l’opérateur peut la clore après son expiration et un contrôle
indépendant confirmant l’absence de tâche native, sans déclarer sa réussite.
Une nouvelle action exige toujours une nouvelle demande SAV explicite.

## Déploiement

Activer `recovery_enabled` uniquement sur les installations qualifiées. Le bootstrap
installe le module du même dépôt, configure sa clé et vérifie démarrage automatique,
version exacte et mises à jour automatiques désactivées. L’agent reste utilisable en
cas d’échec du bootstrap. Une installation dont l’envoi est incertain n’est pas rejouée.
Avant une maintenance Core, le portail exige un secours connecté et un redémarrage
de l’agent effectivement confirmé via cette voie. La version Core reste visible au SAV.

## Recette indispensable avant généralisation

Sur la box pilote, vérifier le diagnostic et un redémarrage réel par le canal HTTPS
indépendant, puis une réparation avec sauvegarde vérifiée, sans utiliser Tailscale
pour ces opérations. Vérifier expiration, révocation, transfert et interruption réseau.
Les tests simulés et les images ARM/x86 ne remplacent pas cette recette matérielle.
Une panne d’alimentation, du stockage, du Supervisor ou de connectivité empêche aussi
ce service : son état doit rester « hors ligne », jamais « réparation réussie ».

Le correctif 0.1.1 utilise les seuls champs acceptés par l’API native de mise à jour (background, backup). Une réponse 4xx explicite est enregistrée comme refus, distinct d’une réponse perdue. Une nouvelle version du secours exige un nouvel essai de redémarrage avant une maintenance Core.
