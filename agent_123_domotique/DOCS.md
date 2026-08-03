# Agent 1.2.3 Domotique

## Configuration

- **Adresse du portail** : conserver l'adresse proposée.
- **Code d'installation** : saisir le code à huit caractères généré depuis le
  dossier d'intervention.
- **Fréquence de synchronisation** : conserver 30 secondes pour les essais.
- **Relais sécurisé** : les trois champs sont préparés par le technicien. Ils
  relient cette box au VPS sans ouvrir de port sur la connexion Internet du client.
- **Caméra traitement piscine** : activer uniquement dans la maison équipée,
  puis conserver l'adresse locale proposée si la caméra ESPHome porte le nom
  `camera-traitement-piscine`. Cette option doit rester désactivée au showroom.

Après le démarrage, le journal doit afficher `Box associée au portail`, puis la
version Home Assistant, les états utiles et le nombre d'entités détectées.

Les commandes envoyées depuis l’application 1.2.3 sont récupérées par l’agent et
exécutées localement. Aucun accès Home Assistant n’est présenté au client.
Le message `Liaison sécurisée VPS active` confirme l'accès distant à l'application.
L’interface visible reste l’application ou le portail 1.2.3 ; l’agent ne
remplace pas le tableau de bord principal de Home Assistant.

En cas de code expiré, générez un nouveau code depuis le portail et remplacez
l'ancien dans la configuration de l'application.

## Traitement de la piscine par caméra

L'agent lit uniquement l'image instantanée locale. Il ne commande jamais les
pompes doseuses. Les entités créées sont :

- `sensor.ph_piscine` ;
- `sensor.orp_piscine` en mV ;
- `binary_sensor.alarme_traitement_piscine` ;
- `binary_sensor.manque_chlore_piscine` ;
- `binary_sensor.communication_traitement_piscine`.

Deux lectures identiques sont exigées avant de publier une nouvelle mesure. Si
l'afficheur pH indique `AL`, le pH devient indisponible et l'alarme de manque de
chlore est activée. Home Assistant affiche alors une notification persistante.
Une perte d'image pendant plus de 90 secondes rend l'état de communication
indisponible sans inventer de mesure.
