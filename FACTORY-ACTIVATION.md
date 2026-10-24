# Activation client sans ordinateur — préparation client

La dépendance à l’assistant Mac concernait la première préparation de Home Assistant et de l’agent, pas les micro-onduleurs. Les box vendues doivent désormais être préparées et contrôlées avant livraison. Un système Home Assistant vierge sans agent ne peut pas être activé à distance par le portail.

## Préparation atelier

1. Initialiser Home Assistant avec une identité d’administration propre à cette unité. Installer la version qualifiée de l’agent depuis le dépôt principal et les connecteurs qualifiés, démarrage automatique activé. Aucun compte partagé ou accès client par l’administration HA.
2. Sur le serveur du portail, exécuter `node scripts/prepare-factory-box.cjs /data/123-home.sqlite <nouveau-dossier-prive> <etiquette>`. Le dossier doit être nouveau ; les fichiers ne sont jamais réécrits. La migration 0054 doit être appliquée.
3. Installer `options-private.json` dans les options de cette seule unité. Ne pas inclure ces secrets dans une image commune, une sauvegarde réutilisée, un journal ou l’étiquette client. Ne jamais cloner `/data/agent-state.json` d’une autre box.
4. Vérifier sur une unité neuve que l’agent attend l’activation, qu’il survit au redémarrage et qu’il revient en ligne sans clé technique saisie chez le client. La présence du fichier registered.json confirme seulement l’enregistrement serveur, pas la qualification matérielle.
5. Fournir l’étiquette activation-label.txt / activation-qr.svg au propriétaire. Elle contient le secret d’activation, distinct du secret de l’agent. Conserver ces fichiers dans l’espace privé de préparation, jamais dans les sources publiques.

## Parcours client

Brancher Ethernet et alimentation → scanner le QR code → se connecter/créer son compte → choisir/créer sa maison → Activer ma box → ajouter les équipements. Le code ne déclenche aucun rattachement automatique. L’utilisateur confirme la maison affichée avant activation.

La box contacte uniquement `https://home.123panneaux-solaires.fr/api/agent/factory` en TLS sortant. Aucune redirection de routeur ni administration publique. Le service LAN 18423 de l’agent permet la preuve d’identité et les échanges chiffrés des téléphones appairés. Le jeton agent est enregistré durablement sur l’unité avant le premier contact. Le serveur conserve uniquement des empreintes ; une réponse perdue reprend la même identité. La box doit avoir contacté le serveur depuis moins de deux minutes pour être associée.

Une box déjà associée conserve sa liaison. Une étiquette utilisée ne remplace jamais une box ou un propriétaire. Les remplacements, cessions et réinitialisations suivent leurs parcours existants. Les anciennes box sans logiciel préparé nécessitent une préparation par l’équipe avant livraison ; retirer le texte « Mac » ne les convertit pas.

## Qualification

Tests automatisés du stockage, de l’isolation des maisons/propriétaires, de la révocation, des reprises, de la persistance et de la destination TLS. La fiche de livraison exige une recette matérielle sur l’unité préparée : redémarrage, coupure et retour d’Internet, persistance des réglages, sauvegarde et récupération. La préparation logicielle seule ne valide pas cette recette. Le showroom déjà associé n’a pas été réinitialisé à nouveau pour cet essai.

## Contrôles avant remise

- Confirmer que la version installée, le paquet qualifié et le catalogue du portail désignent le même contenu.
- Configurer pays, fuseau et localisation ; vérifier la copie locale de la révision courante.
- Activer le démarrage automatique et le chien de garde ; désactiver les mises à jour automatiques non qualifiées.
- Planifier les sauvegardes locales, vérifier la destination distante si activée, conserver le kit de secours hors de la box.
- Vérifier la capacité du stockage distant avant toute nouvelle activation. Une réserve disque insuffisante doit bloquer les nouveaux envois.
- Conserver la fiche de recette de l’unité et les versions/empreintes des images installées.


## Sortie HDMI et maintenance technique

La préparation HDMI est une étape atelier distincte, documentée dans `labox_boot_prepare/README.md`. Sur les box sans écran, aucun tableau de bord HAOS n’est présenté en HDMI. Sur une console, l’application reste le point d’entrée visuel.

Avant d’appliquer le profil de démarrage, préparer le module local `labox_maintenance` et son kit technique propre à cette unité. Tester l’authentification par clavier USB, l’expiration de la session et le retour à l’app ; archiver sauvegarde de démarrage, empreintes et kit privé hors des images réutilisables. Ces deux modules sont expérimentaux jusqu’à la recette physique sur chaque type de matériel livré.

Le raccourci et le code de maintenance restent dans la documentation équipe. Après une mise à jour HAOS, auditer et requalifier l’affichage et l’accès local ; aucune modification silencieuse du démarrage n’est effectuée par l’agent.
