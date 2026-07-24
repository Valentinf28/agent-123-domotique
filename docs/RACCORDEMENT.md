# Raccordement de la maison connectée

La première version utilise des données de démonstration réalistes. L’interface est volontairement découplée du système domotique. Un connecteur de lecture local est disponible dans `lib/home-connector.ts`.

## Test local

Configurer `HA_BASE_URL`, `HA_ACCESS_TOKEN` et `HA_ALLOW_LOCAL_DEVELOPMENT=true`
dans `.env.local`. Ce fichier est ignoré par Git. Le jeton n’est jamais renvoyé au
navigateur. La route `/api/home` transforme les états en objets publics et remplace
les identifiants techniques par des identifiants opaques.

## Architecture cible

1. Le navigateur appelle uniquement les routes `/api/*` du portail.
2. La route authentifie l’utilisateur et résout côté serveur son `home_id` et son rôle.
3. Le service d’autorisation vérifie que l’utilisateur appartient à cette maison et que l’action est permise.
4. Un connecteur serveur appelle l’API de la maison avec un secret stocké dans l’environnement d’hébergement.
5. Le serveur traduit les données techniques vers des identifiants opaques et des libellés conviviaux.
6. Les opérations sensibles demandent une confirmation dans l’interface, puis sont journalisées côté serveur.

## Décisions restantes

- Choisir l’identité client définitive : comptes propres à Ma Maison ou fournisseur d’identité existant.
- Définir le registre des maisons : utilisateur, rôle, maison, installation et connecteur.
- Choisir le canal privé vers chaque installation : tunnel sortant, service central ou passerelle installateur.
- Définir la stratégie de rotation et de révocation des secrets.
- Valider les capacités autorisées par type d’appareil et le format des automatisations.

## Contrat de sécurité

- Aucun jeton domotique dans le navigateur, le code client ou le dépôt.
- Aucune donnée technique brute ou identifiant d’entité transmis au client.
- Contrôle d’accès par maison et par rôle sur chaque lecture et écriture.
- Liste blanche d’actions exposées par la façade serveur.
- Journal d’audit immuable pour les renommages, déplacements, ajouts, suppressions et règles.
- Protection CSRF, limitation de débit, validation stricte des entrées et secrets hébergés uniquement côté serveur.

Le point d’entrée initial est `app/api/home/route.ts`. Il refuse les utilisateurs non authentifiés et matérialise la frontière serveur.
