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

Les lectures normales sont espacées de cinq minutes et deux lectures identiques
sont exigées avant de publier une nouvelle mesure. Les transitions d'alarme sont
confirmées par une seconde image après 15 secondes. Si
l'afficheur pH indique `AL`, le pH devient indisponible et l'alarme de manque de
chlore est activée. Home Assistant affiche alors une notification persistante.
Une perte d'image pendant plus de 15 minutes rend l'état de communication
indisponible. La dernière mesure valide reste affichée au lieu d'être remplacée
par une valeur inventée ou momentanément illisible.
## Recherche solaire de mise en service (en développement)

La commande `commissioning.discover_solar` interroge les interfaces actives de
la box puis recherche les loggers SolarMAN en UDP. Un passage TCP limité au
port 8899 complète la recherche sur les sous-réseaux de 256 adresses maximum.
Aucun hôte, masque ou port transmis par le demandeur n'est utilisé. Les appareils
TCP sans annonce d'identité restent « à identifier » ; aucun profil ni association
n'est créé. Le résultat n'atteste pas la compatibilité d'un onduleur.

Le mode réseau hôte est nécessaire pour envoyer les annonces depuis les interfaces
de la box. Aucun serveur entrant n'est ajouté. Cette modification reste à tester
sur HAOS avant publication. Le portail n'appelle pas encore cette commande.

Validation du 7 octobre 2026 : exécution du module depuis le Mac sur le réseau
Showroom, logger UDP trouvé en .66 et candidat TCP en .178. La connexion autonome
depuis la box, l'installation de SolarMAN et le parcours portail restent à valider.
