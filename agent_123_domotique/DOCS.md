# Agent 1.2.3 Domotique

## Configuration

- **Adresse du portail** : conserver l'adresse proposée.
- **Code d'installation** : saisir le code à huit caractères généré depuis le
  dossier d'intervention.
- **Fréquence de synchronisation** : conserver 30 secondes pour les essais.
- **Relais sécurisé** : les trois champs sont préparés par le technicien. Ils
  relient cette box au VPS sans ouvrir de port sur la connexion Internet du client.

Après le démarrage, le journal doit afficher `Box associée au portail`, puis la
version Home Assistant et le nombre d'entités détectées.
Le message `Liaison sécurisée VPS active` confirme l'accès distant à l'application.

En cas de code expiré, générez un nouveau code depuis le portail et remplacez
l'ancien dans la configuration de l'application.
