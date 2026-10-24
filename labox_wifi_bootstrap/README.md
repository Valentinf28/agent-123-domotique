# Première connexion Wi-Fi — candidat 0.1.0

Module HAOS séparé de l’agent. **Expérimental : validation sur une box neuve et sa clé Wi-Fi obligatoire avant livraison.** Aucun réseau d’une box existante n’est modifié par sa simple installation : `armed` vaut `false` par défaut.

## Parcours client

1. Brancher la box sans Ethernet et patienter pendant son démarrage.
2. Scanner l’étiquette individuelle, rejoindre `LaBox-XXXXXX` et rester connecté malgré l’indication « sans Internet ».
3. La fenêtre de configuration peut s’ouvrir automatiquement. Sinon ouvrir l’adresse imprimée : `http://192.168.77.1:18424`.
4. Sélectionner ou saisir le nom du Wi-Fi de la maison et son mot de passe. WPA2 personnel/AES uniquement dans cette première version ; pas de réseau ouvert, entreprise, ou WPA3 seul.
5. Attendre jusqu’à 150 secondes. Le téléphone perd temporairement le réseau LaBox pendant que l’unique radio rejoint la maison.
6. En cas d’échec, le réseau de configuration revient : le client le rejoint pour lire le résultat et corriger. En cas de succès, le client rejoint son Wi-Fi habituel et active sa box dans `/ma-maison`.

Le point d’accès s’arrête après 15 minutes, y compris si le processus de configuration plante (expiration NetworkManager). Un redémarrage complet autorise une nouvelle fenêtre uniquement pour une première installation encore inachevée. Une box installée ou dont un réseau personnel existe n’ouvre pas ce point d’accès lors d’une panne Internet.

## Préparation atelier (à intégrer dans l’image des box neuves)

- Agent candidat 0.6.35 : publie uniquement un marqueur local non secret, rafraîchi à chaque cycle. Le module exige un marqueur récent et une préparation usine valide sans identité client déjà associée.
- Installer ce module sans l’armer ; exécuter `python preflight.py` (lecture seule) pour vérifier la MAC permanente et les capacités AP + WPA2/AES de la **clé réellement livrée**. La présence d’une clé USB et le fonctionnement client ne prouvent pas la capacité AP.
- Après préparation usine, renseigner `factory_context` (SHA-256 de l’identifiant usine, jamais le token usine), `wifi_mac`, et `armed: true`.
- Conserver l’Ethernet pendant cette préparation : le module génère ses propres identifiants de configuration, mais attend et ne remplace pas le réseau de l’atelier.
- Exporter l’étiquette privée dans le conteneur : `python workshop.py --output /data/etiquette.html`, puis la récupérer par le canal atelier authentifié. Le fichier contient la clé du réseau temporaire : ne pas le publier, ni l’inclure dans une image clonée.
- Ne jamais cloner `/data/onboarding.json` entre box. Il contient SSID, mot de passe et UUID uniques. L’activation propriétaire existante reste une étape distincte.
- Avant une nouvelle cession : terminer le processus normal de sauvegarde/réinitialisation/identité usine. Arrêter ce module, supprimer ses données d’onboarding **après** leur retrait de l’ancienne installation et recréer l’étiquette. Aucun réarmement public n’existe dans l’interface client.

## Limites de privilèges

Le module utilise D-Bus hôte pour NetworkManager, le réseau hôte et NET_ADMIN/NET_RAW pour DHCP, DNS, filtrage local et contrôle HTTPS lié à l’interface Wi-Fi. Aucune API HA, API Supervisor, socket Docker, accès global aux périphériques, mode privilégié intégral ou PID hôte. Le répertoire de configuration HA est monté en lecture seule pour le seul marqueur ; le module ne lit aucun secret de HA.

Le serveur écoute uniquement sur l’adresse AP. Filtrage IPv4/IPv6 lié à la seule interface AP, isolation des clients, aucun transfert vers le LAN. Seul HTTP est redirigé pour la détection captive ; HTTPS n’est jamais intercepté. Origin, Host canonique, jeton CSRF, taille des requêtes, concurrence et fréquence sont contrôlés. Aucun mot de passe dans les arguments de processus, journaux ou réponses publiques. Les identifiants du Wi-Fi maison sont transmis directement à NetworkManager par D-Bus et persistés seulement après vérification DHCP + HTTPS du portail par l’interface candidate.

Deux points de reprise indépendants du Mac : expiration de la session AP (900 s, interface Wi-Fi seulement), puis tentative station (150 s, chevauchement limité au point de reprise du module). Aucun effacement global de profils ou points de reprise. En cas de crash, le journal reprend par annulation ; aucune réussite n’est déduite d’un état ancien. Les profils d’autres connexions et l’Ethernet ne sont jamais supprimés/modifiés. En cas d’échec du retour réseau, le module ne prétend pas être prêt et conserve le filtrage jusqu’à nettoyage sûr.

## Qualification indispensable sur le matériel

Valider sur ODROID/HAOS et la clé livrée : démarrage sans câble, scan/iPhone/Android, QR et fenêtre captive, saisie manuelle SSID masqué, mauvais mot de passe, DHCP indisponible, routeur sans Internet, redémarrage pendant tentative, crash du module, expiration autonome 15 min, connexion réussie et redémarrage, absence d’AP après activation/panne Internet, retrait de la clé USB. Garder l’Ethernet comme secours physique pour ces premiers tests. Le test ne doit pas être fait sur une installation client active.

Références : [HAOS et NetworkManager](https://contributors.home-assistant.io/os/operating-system/networking/), [configuration des modules](https://contributors.home-assistant.io/apps/reference/configuration/), [API NetworkManager et points de reprise](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html), [types des points de reprise](https://networkmanager.dev/docs/api/1.48/nm-dbus-types.html).
