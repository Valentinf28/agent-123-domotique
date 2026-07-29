# Agent 1.2.3 Domotique

## Configuration

- **Adresse du portail** : conserver l'adresse proposée.
- **Code d'installation** : saisir le code à huit caractères généré depuis le
  dossier d'intervention.
- **Fréquence de synchronisation** : conserver 30 secondes pour les essais.
- **Relais sécurisé** : les trois champs sont préparés par le technicien. Ils
  relient cette box au VPS sans ouvrir de port sur la connexion Internet du client.

Après le démarrage, le journal doit afficher `Box associée au portail`, puis la
version Home Assistant, les états utiles et le nombre d'entités détectées.

Les commandes envoyées depuis l’application 1.2.3 sont récupérées par l’agent et
exécutées localement. Aucun accès Home Assistant n’est présenté au client.
Le message `Liaison sécurisée VPS active` confirme l'accès distant à l'application.
Le message `Tableau de bord 1.2.3 Home mis à jour` confirme que les onglets et
les appareils validés dans le portail ont été appliqués automatiquement.

En cas de code expiré, générez un nouveau code depuis le portail et remplacez
l'ancien dans la configuration de l'application.
