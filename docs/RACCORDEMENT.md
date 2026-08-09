# Raccordement de la maison connectée

L’interface client est volontairement découplée du système domotique. Les états
remontent par l’Agent 1.2.3 et les commandes repartent vers la box 1.2.3. Home par une
file privée. Home Assistant n’est jamais chargé dans l’application cliente.

## Test local

L’agent remonte un inventaire au portail. La route `/api/home` sélectionne la box
du dossier, transforme les états en objets publics et remplace les identifiants
techniques par des identifiants opaques. Une commande cliente est placée dans la
file du dossier, récupérée au prochain contact de l’agent, puis exécutée
localement.

La box 1.2.3. Home envoie les mesures importantes toutes les 5 secondes et un
inventaire complet toutes les 60 secondes. La vue client relit automatiquement
`/api/home` au rythme de 5 secondes et le bouton d’actualisation force une
lecture immédiate. Les onglets Énergie, Confort, Piscine, Sécurité et Véhicule
reconstituent dans le portail la vue domotique utile au client, sans charger ni
exposer l’interface Home Assistant.

## Architecture cible

1. Le navigateur appelle uniquement les routes `/api/*` du portail.
2. La route authentifie l’utilisateur et résout côté serveur son `home_id` et son rôle.
3. Le service d’autorisation vérifie que l’utilisateur appartient à cette maison et que l’action est permise.
4. L’agent établit uniquement des connexions sortantes et garde le jeton Home Assistant dans la box.
5. Le serveur traduit les données techniques vers des identifiants opaques et des libellés conviviaux.
6. Les commandes autorisées passent par une liste blanche et une file rattachée au dossier.
7. Les opérations sensibles demandent une confirmation dans l’interface, puis sont journalisées côté serveur.

## Décisions restantes

- Choisir l’identité client définitive : comptes propres à Ma Maison ou fournisseur d’identité existant.
- Définir le registre des maisons : utilisateur, rôle, maison, installation et connecteur.
- Définir la stratégie de rotation et de révocation des secrets.
- Valider les capacités autorisées par type d’appareil et le format des automatisations.

## Contrat de sécurité

- Aucun jeton domotique dans le navigateur, le code client ou le dépôt.
- Aucune donnée technique brute ou identifiant d’entité transmis au client.
- Contrôle d’accès par maison et par rôle sur chaque lecture et écriture.
- Liste blanche d’actions exposées par la façade serveur.
- Journal d’audit immuable pour les renommages, déplacements, ajouts, suppressions et règles.
- Protection CSRF, limitation de débit, validation stricte des entrées et secrets hébergés uniquement côté serveur.
- Aucun iframe, lien ou redirection vers Home Assistant dans le parcours client.
- Accès Home Assistant direct réservé au support, hors de l’application client.

Le point d’entrée initial est `app/api/home/route.ts`. Il refuse les utilisateurs non authentifiés et matérialise la frontière serveur.
