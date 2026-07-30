# Journal des versions

## 0.5.15

- Calcule la consommation journalière directement depuis le compteur d’énergie Shelly.
- Calcule également l’achat et l’injection réseau journaliers depuis le Shelly.
- Conserve les compteurs Deye uniquement comme solution de repli.

## 0.5.14

- Corrige la cadence de synchronisation pour démarrer un cycle toutes les cinq secondes, temps de lecture et de transmission compris.

## 0.5.13

- Aligne les flux du portail sur les compteurs Shelly utilisés par la vue énergie Home Assistant.
- Rafraîchit la consommation maison et le réseau toutes les cinq secondes.

## 0.5.12

- Prise en charge directe des capteurs Open-Meteo Solar Forecast.
- Sélection automatique de la première source solaire réellement disponible.
- Repli transparent lorsque Forecast.Solar est présent mais indisponible.

## 0.5.11

- Utilisation automatique des capteurs Forecast.Solar actifs par défaut.
- Prise en charge de l'énergie restante aujourd'hui et de la prévision de demain.
- Aucune activation manuelle de capteur requise sur la box client.

## 0.5.10

- Contournement du défaut Forecast.Solar de Home Assistant 2026.7.2.
- Reconstruction locale d'une courbe sur 24 heures à partir des capteurs Forecast.Solar.
- Conservation de la courbe native comme source prioritaire lorsqu'elle est disponible.

## 0.5.9

- Récupération de la courbe solaire horaire fournie par Home Assistant.
- Mise en cache locale des prévisions afin de limiter les appels au service météo.
- Transmission des créneaux prévisionnels au moteur de pilotage 1.2.3 Home.

## 0.5.8

- Rafraîchissement des mesures importantes toutes les 5 secondes.
- Inventaire complet conservé toutes les 60 secondes pour limiter le trafic.
- Envoi intermédiaire compact pour l’énergie, le confort, la piscine, la sécurité et les véhicules.

## 0.5.6

- Conservation de l'environnement sécurisé Home Assistant lors du démarrage autonome.

## 0.5.5

- Démarrage autonome de l'agent, sans dépendance au lanceur `with-contenv`.
- Journal de démarrage disponible immédiatement pour faciliter la recette en atelier.

## 0.5.4

- Allongement du délai des commandes lentes, notamment le réveil et le pilotage des véhicules Tesla.

## 0.5.3

- Suppression complète de toute écriture et restauration automatique des tableaux de bord Lovelace.

## 0.5.2

- Restauration automatique du tableau de bord principal depuis la vue préservée `123-maison`.
- Désactivation de toute écriture automatique sur le tableau de bord principal Home Assistant.

## 0.5.1

- Correction de l'identification réseau de l'agent auprès du portail privé.
- Suppression du refus HTTP 403 lors de la synchronisation.

## 0.5.0

- Remontée de l'inventaire Home Assistant vers le portail technicien.
- Réception des associations validées par le technicien.
- Génération et mise à jour automatique du tableau de bord Lovelace.
- Conservation du tableau de bord existant tant qu'aucun appareil n'est associé.
# 0.5.7

- Ajout d’une file de commandes privée entre le portail 1.2.3 et la Green Box.
- Les commandes clientes sont exécutées localement sans exposer Home Assistant.
- Rafraîchissement ramené à 10 secondes pour le pilotage de démonstration.
