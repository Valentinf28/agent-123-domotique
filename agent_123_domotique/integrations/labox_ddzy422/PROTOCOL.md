# Lecteur local DDZY422-D2

Le protocole AT+INVDATA sur UDP 48899 a été documenté par :
https://github.com/Pengo-fmm/ddzy422-local
https://github.com/davidrapan/ha-solarman/issues/187

Implémentation La Box issue de notre lecture matérielle du 14 octobre 2026 :
DDZY422-D2, firmware LSW3_15_E030_1.05, identité MAC + numéro vérifiés,
FC03 uniquement, blocs (0,14) et (14,20), trames et CRC contrôlés.
Aucune commande de configuration, aucune écriture de registre, aucun cloud.
Une puissance positive est du soutirage ; une puissance négative de l’injection.

Entités Home Assistant natives : les index physiques kWh utilisent ENERGY et
TOTAL_INCREASING. Les index sont conservés au rechargement et ne peuvent pas
diminuer ou dépasser la borne physique sans rendre les mesures indisponibles.
Aucune correction inventée ou valeur zéro lors d’une panne. Un remplacement ou
une remise à zéro matérielle demande une intervention explicite sur les index
et les statistiques ; cette première version ne réinitialise jamais ceux-ci.

Un seul client local par numéro, mise à jour toutes les 30 secondes. Tout échec
rend les entités indisponibles. Le premier déploiement du composant nécessite
un redémarrage Home Assistant explicite après sa sauvegarde ; l’installateur
ne déclenche aucun redémarrage. Les fichiers tiers sont toujours conservés.
Les paramètres et jalons d’index sont stockés localement par Home Assistant.
