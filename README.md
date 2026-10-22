# Agent La Box — préparation et exploitation

Application Home Assistant OS pour associer une unité au portail client 1.2.3 Home, remonter les appareils et permettre les commandes prévues pour cette maison.

## Référence d’installation

Le dépôt de livraison est `https://github.com/Valentinf28/agent-123-domotique`, branche `main`. L’équipe prépare les box en atelier avant livraison. Une box Home Assistant vierge ne peut pas être activée par un simple lien du portail.

L’installation utilise le portail `https://home.123panneaux-solaires.fr/api`. Les échanges distants utilisent HTTPS/WSS et refusent les redirections authentifiées. Aucun port entrant ne doit être ouvert sur le routeur du client.

La branche `codex/automatic-box-relay` est une branche de préparation et de compatibilité pour les unités pilotes. Le catalogue du portail doit référencer le commit exact qualifié ; un numéro de version seul n’atteste pas un binaire testé.

## Préparation d’une unité

Suivre [FACTORY-ACTIVATION.md](FACTORY-ACTIVATION.md). Chaque unité reçoit sa propre identité, ses propres secrets et un compte administrateur HA distinct. Ne jamais cloner l’identité ou une sauvegarde du showroom pour fabriquer une autre box.

La remise au client exige une copie locale des réglages confirmée, une sauvegarde récupérable, un démarrage automatique vérifié et une fiche de recette liée à l’unité. Une restauration remplace l’installation : aucune seconde box ne doit fonctionner avec la même identité.

## Données et accès

L’agent transmet la version HA, les états et les attributs autorisés des entités, leur identité d’intégration et les résultats des opérations demandées. Les tokens internes HA ne sont pas envoyés aux téléphones.

Le service LAN sur le port 18423 fournit une preuve d’identité et un accès mobile appairé chiffré, protégé contre les rejeux et limité aux commandes autorisées. HA conserve son interface d’administration locale, réservée à l’équipe. L’agent demande le réseau hôte, le rôle Supervisor manager et l’écriture dans la configuration HA pour ses fonctions de préparation et de maintenance. Ces accès sont puissants et ne doivent pas être exposés publiquement.

La copie locale contient uniquement les réglages applicatifs autorisés, y compris le suivi énergétique. Le lecteur valide aussi les capteurs et la fraîcheur de leurs mesures avant de calculer un bilan. Une indisponibilité ne devient pas une mesure à zéro.

## Qualification d’une version

Installer les dépendances de `agent_123_domotique/requirements.lock`, puis exécuter :

```
python scripts/package_manifest.py --check
python tests/run_isolated.py
```

La CI construit ensuite le paquet complet sur amd64 et arm64 et lance `release_smoke.py` sans réseau ni données persistantes inscriptibles. Elle vérifie l’empreinte de tous les fichiers empaquetés et importe les modules réels. Toute modification d’un fichier empaqueté exige de régénérer le manifeste avec `python scripts/package_manifest.py`.

Les versions Python et l’image de base sont figées. Les versions des paquets système et l’identité de l’image réellement construite sont conservées dans la preuve de qualification. Un changement de dépendance nécessite une nouvelle qualification.

La réussite de la CI ne remplace pas les essais matériels : redémarrage électrique, perte et retour d’Internet, réseau DHCP, mise à jour et restauration complète. Une version ou une unité non qualifiée reste en préparation.

## Sauvegardes

Conserver une copie locale quotidienne et une copie distante selon les droits de l’installation. Vérifier l’envoi d’une archive chiffrée et une restauration réelle. Le kit de secours contenant la clé doit être conservé hors de la box et hors du serveur de sauvegarde ; il ne doit jamais être commité ni journalisé.

## Reprise accompagnée

Le champ privé `restore_identity` sert uniquement à reprendre une identité de sauvegarde existante dans un état vide. Il vérifie la maison auprès du portail HTTPS et n’écrase pas une autre identité. Arrêter l’ancien agent avant reprise, puis vider ce champ après validation. Les cessions et remises à zéro suivent leurs opérations dédiées et sauvegardées.
