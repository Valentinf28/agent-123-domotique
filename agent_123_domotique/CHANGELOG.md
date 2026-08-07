# Journal des versions

## 0.5.48

- Ajoute une politique Deye optionnelle liée au branchement physique du véhicule.
- Coupe uniquement `Solar Sell` après 30 secondes de débranchement et le réactive après 10 secondes de branchement.
- Synchronise immédiatement `Solar Sell` avec l’état actuel de la prise lors de l’installation de la règle.
- Ne change jamais le mode général de l'onduleur et n'écrit directement dans aucun registre Modbus.
- Restaure l'injection normale lorsque le mode de recharge solaire est désactivé depuis l'application.

## 0.5.47

- Corrige la confusion résiduelle qui pouvait lire `69` comme `33` sur l'afficheur chlore multiplexé.
- Empêche la règle rapide du chiffre `3` de masquer les segments gauches réellement allumés des chiffres `6` et `9`.
- Fait primer le vote des images individuelles sur l'artefact temporel connu `33`.

## 0.5.46

- Corrige la confusion du lecteur caméra qui pouvait transformer `66` ou `68` en `33`.
- Publie désormais le chlore sous sa forme normalisée en mV : `66` affiché devient `660 mV`.
- Conserve la valeur brute de l'afficheur dans les attributs pour le diagnostic.

## 0.5.45

- Rend la rafale de la caméra piscine adaptative afin de couvrir systématiquement le cycle complet des afficheurs multiplexés.
- Fiabilise la lecture simultanée de l'alarme pH `AL` et de la valeur chlore affichée.
- Publie immédiatement une alarme déjà confirmée par plusieurs images de la même rafale.

## 0.5.44

- Espace les neuf captures de la rafale afin de couvrir un cycle complet du balayage des afficheurs.
- Évite les rafales composées de neuf phases noires identiques qui masquaient l'alarme pH `AL`.

## 0.5.43

- Reconnaît l'alarme pH `AL` sur plusieurs phases complètes de l'afficheur multiplexé.
- Ignore les images intermédiaires qui ne montrent que le point lumineux.
- Ne confond plus un pH réel de 9,1 avec l'alarme `AL`.

## 0.5.42

- Corrige les confusions du multiplexage qui pouvaient transformer `AL` en `91` et `69` en `33`.
- Fait primer le consensus de la rafale sur une lecture temporelle contradictoire.
- Remplace l'état trompeur « connectée » par « lecture non confirmée » ou « périmée » lorsque l'image est reçue mais illisible.
- Expose la dernière lecture brute et sa confiance dans le diagnostic Home Assistant.

## 0.5.41

- Fiabilise le démarrage du lecteur caméra piscine et le relance automatiquement en cas d'arrêt.
- Ajoute un diagnostic visible dans Home Assistant avec l'état et l'erreur éventuelle de la caméra.
- Journalise clairement chaque mesure pH/chlore publiée.

## 0.5.40

- Confirme séparément l’alarme pH et la valeur chlore afin qu’une variation OCR ne bloque plus `AL`.
- Publie la valeur visible du chlore dans `sensor.chlore_piscine` tout en conservant l’ORP en mV.
- Rend les mesures indisponibles après quinze minutes sans lecture validée au lieu d’afficher d’anciennes valeurs.
- Signale `AL` comme une alarme pH sans l’interpréter à tort comme un manque de chlore.

## 0.5.39

- Supprime la marge d’injection permanente de la recharge solaire Lektrico.
- Vise l’équilibre réseau avec un arrondi au palier d’ampérage le plus proche.
- Autorise, après 95 % de batterie domestique, une aide transitoire limitée à un demi-palier, soit environ 115 W en monophasé.

## 0.5.37

- Lit les deux chiffres Redox sur l'ensemble de la rafale au lieu de traiter chaque image isolément.
- Compense le balayage lumineux et le halo des petits afficheurs avec un profil sept segments spécialisé.
- Valide sur les images réelles `36`, `37` puis `43`, soit `360`, `370` et `430 mV`, avec la caméra unique.

## 0.5.36

- Refuse les correspondances OCR de faible confiance qui pouvaient transformer `37` en `23` lorsque les chiffres sont trop petits dans l'image.
- Conserve la dernière mesure réellement fiable au lieu de publier une nouvelle valeur chimique douteuse.

## 0.5.35

- Recalibre les zones pH et ORP pour la position définitive de la caméra.
- Sépare les chiffres reliés par le halo sans partager leur pixel central, ce qui corrige `36` en `360 mV`.
- Reconnaît les segments orange saturés du nouveau cadrage plus lumineux.

## 0.5.34

- Vote séparément sur chaque chiffre ORP à partir de neuf captures pour éliminer les phases parasites du multiplexage.
- Ignore une variation de pH supérieure à 0,5 entre deux cycles et conserve la dernière mesure cohérente.

## 0.5.33

- Lit désormais chaque afficheur sur une rafale de cinq images afin de neutraliser son multiplexage.
- Empêche qu'un affichage physique `39` soit capturé suivant la phase comme `86`, `88` ou `29`.

## 0.5.32

- Corrige la confusion OCR entre le chiffre `9` du Micro Rx et la lettre `A` réservée à l'alarme pH.
- Une lecture visuelle `39` est désormais publiée comme `390 mV`, sans conserver une ancienne valeur erronée.

## 0.5.31

- Espace les lectures normales de la caméra piscine à cinq minutes.
- Conserve la dernière mesure valide lorsqu'une image intermédiaire est illisible.
- Confirme les débuts et fins d'alarme après 15 secondes et signale une liaison périmée après 15 minutes.

## 0.5.30

- Corrige la séparation des chiffres lorsque le halo de l'afficheur ne les relie pas.
- Lit correctement les affichages réels `9.1` et `42`, soit `420 mV` pour l'ORP.

## 0.5.29

- Ajoute la lecture locale des afficheurs AstralPool par la caméra ESPHome de la piscine.
- Publie le pH, l'ORP, l'état de communication et l'alarme de manque de chlore dans Home Assistant.
- Ajoute une notification persistante en cas de manque de chlore, sans aucune commande des pompes doseuses.

## 0.5.28

- Limite chaque demande d'historique à la journée sélectionnée dans l'application.
- Rétablit les données et le graphique lors de la consultation d'un jour précédent.
- Allège les réponses Home Assistant pour accélérer le chargement du calendrier solaire.

## 0.5.27

- Conserve la régulation solaire Lektrico fiabilisée et son redémarrage automatique.
- Ajoute le mode de recharge Lektrico pendant une ou plusieurs plages d'heures creuses.
- Enrichit l'inventaire transmis au portail avec les métadonnées sûres du registre Home Assistant pour faciliter la découverte et le préparamétrage des appareils.

## 0.5.26

- Respecte les 45 secondes de tolérance avant d’arrêter une recharge dont le surplus devient insuffisant.
- Ne coupe plus la borne pendant les quelques secondes nécessaires au démarrage de la voiture.
- Relance automatiquement la recharge toutes les 15 secondes tant que la voiture est prête et que le surplus reste suffisant.

## 0.5.25

- Laisse à la borne le temps de stabiliser sa mesure après l'enclenchement du relais.
- Utilise la limite demandée tant que le courant réel Lektrico n'est pas encore remonté.
- Évite les démarrages suivis d'une coupure cinq secondes plus tard malgré un surplus suffisant.

## 0.5.24

- Empêche la recharge solaire Lektrico d'utiliser la batterie domestique.
- Donne la priorité à la batterie de la maison jusqu'à 95 %, puis utilise le surplus exporté.
- Réduit automatiquement l'intensité dès que la batterie commence à se décharger.
- Arrête la recharge lorsque le surplus réel ne permet plus de maintenir 6 A.

## 0.5.23

- Aligne les données du portail avec celles de l’application mobile.
- Transmet les températures, consignes, états météo, piscine, Tesla et Lektrico utiles.
- Ajoute les consommations journalières de la filtration, de la PAC piscine, du chauffe-eau et de la recharge véhicule.
- Accélère la remontée des équipements importants toutes les cinq secondes.

## 0.5.22

- Autorise le redémarrage solaire quand une voiture branchée attend l'autorisation de la borne.
- Prend aussi en charge une recharge mise en pause par le programmateur Lektrico.

## 0.5.21

- Accélère la régulation locale Lektrico avec un contrôle toutes les 5 secondes.
- Arrête réellement la borne lorsque le surplus devient insuffisant au lieu de demander une limite invalide de 0 A.
- Évite que la recharge reste physiquement à 6 A alors que l’application affiche 0 A.

## 0.5.20

- Ajoute la régulation locale de la borne Lektrico sur le surplus solaire.
- Ajuste la limite dynamique toutes les 15 secondes avec une marge anti-import.
- Arrête la recharge en cas d’import réseau persistant ou de défaut de la borne.

## 0.5.19

- Unifie les cumuls énergétiques jour, mois et année utilisés par l’application et le portail.
- Conserve Deye pour la production et Shelly pour la consommation et les échanges réseau.

## 0.5.18

- Fiabilise `sensor.pic_pv_jour` directement depuis la puissance photovoltaïque.
- Conserve le maximum atteint pendant la journée dans le fuseau horaire de la maison.
- Réinitialise automatiquement le pic à minuit, même si les anciennes automatisations sont indisponibles.

## 0.5.17

- Ajoute l’installation sécurisée d’une règle ECS pilotée par le surplus solaire.
- Conserve une plage de secours configurable lorsque la production est insuffisante.
- Laisse le thermostat interne du ballon interrompre naturellement la chauffe.

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
