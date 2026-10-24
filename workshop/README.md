# Repérage atelier et gravure — box et console

Le numéro de série et le code Wi-Fi sont indépendants. Exemple : `LB-A4C7E2F9`, réseau `LaBox-A4C7E2F9`, code de huit caractères. Pour une console : préfixes `LC-` et `LaConsole-`.

Le code individuel est généré par l'appareil lors de sa préparation, pas par le graphiste. Il contient huit chiffres et lettres majuscules, au moins un de chaque, sans O/0 ni I/1. Un redémarrage ou une mise à jour ne le change pas. L'identité complète reste liée à son contexte usine ; les références abrégées ne remplacent ni l'identité technique ni les codes propriétaire/SAV.

## Préparation

Dans le module Wi-Fi de la box neuve préparée :

```
python workshop.py --format identification --product box --output /data/identification-private.json
```

Récupérer cet export privé sur le poste atelier par le canal déjà authentifié. Ne pas copier l'état complet d'onboarding ni une identité d'une carte vers une autre.

Sur le poste atelier, dans un environnement Python dédié :

```
python -m pip install -r workshop/requirements.txt
python workshop/identification.py --identity /chemin/identification-private.json --output /chemin/registre-atelier/unite-LB-A4C7E2F9
```

Conserver les kits sous le même répertoire atelier pour détecter une référence abrégée déjà utilisée avec une autre identité. Réimprimer les fichiers du kit existant ; ne pas fabriquer de nouvel identifiant à chaque impression. Le code ne passe jamais en argument de commande ni dans la sortie console.

## Supports

- `boitier-chene.svg/png` et `carte-odroid.svg/png` : deux étiquettes de repérage ayant exactement la même référence. Pas de mot de passe sur ces étiquettes internes.
- `imprimer-etiquettes.html` : une page par étiquette, impression à 100 %, sans ajustement ni entête navigateur. Par défaut 54 × 25 mm, gabarit provisoire à régler au modèle et consommable Dymo réellement utilisés (`--label-width` / `--label-height`). Pas de commande d'impression automatique ni de pilote Dymo installé.
- `maquette-gravure.svg/png` : dos de l'appareil, 80 × 45 mm. SVG en millimètres et textes convertis en tracés, PNG à 600 dpi. Le cadre du document n'est pas une ligne de découpe. Importer dans LightBurn, vérifier la taille, puis qualifier la gravure sur une chute du même chêne. Aucun G-code ou réglage puissance/vitesse n'est imposé.
- `identification-private.json` : source exacte pour réimpression. Chaque kit est privé, permissions 0700/0600. Ne pas le publier ni l'inclure dans une image clonée.

Les exports démo sont marqués **SPÉCIMEN / CODE FICTIF**. Le gabarit console utilise une identité fictive ; le parcours console devra fournir son propre export réel et son réseau correspondant. Ce générateur ne déploie pas de point d'accès sur une console existante.

## Marquages du produit assemblé

Les coordonnées de la maquette proviennent des publications de SAS 123 PANNEAUX SOLAIRES : 14 rue du Vieux Pont, 28380 Saint-Rémy-sur-Avre, France. Le fabricant qui met l'ensemble sur le marché sous sa marque assume les obligations applicables à l'ensemble ; les déclarations des composants ne valent pas à elles seules déclaration du produit final.

Les références modèles `HOME-B01` et `HOME-C01` sont proposées pour la maquette. L'alimentation de l'appareil complet reste à renseigner : la recommandation 5 V / 3 A de la seule carte ODROID-M1S ne prouve pas les caractéristiques de la console assemblée. Le nom et l'adresse postale du fabricant sont prévus conformément à l'article 10 §7 de la directive RED, sous réserve de l'analyse réglementaire du produit réel.

Le CE reprend les tracés de l'EPS officiel de la Commission, sans déformation, hauteur 6 mm. La poubelle barrée et la barre de datation figurent sur la maquette ; sa reproduction doit être validée avant fabrication. `markingReviewed` reste `false` : ces fichiers ne constituent pas une évaluation ou une déclaration de conformité. Une configuration fabricant revue peut être fournie via `--maker`. Le générateur ne recherche ni ne crée un certificat CE.

La signalétique Info-tri française est à préparer séparément sur l'emballage ou la notice à partir du kit de l'éco-organisme applicable : la seule poubelle barrée ne couvre pas toutes les obligations d'information de tri. Aucun faux logo RoHS, classe électrique, indice IP, numéro d'organisme notifié ou origine France n'est ajouté.

Sources officielles et techniques : voir `assets/sources.json`.
