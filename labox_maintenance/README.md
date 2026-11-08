# Maintenance locale HDMI — candidat 0.1.0

Accès réservé à l’équipe : clavier USB, combinaison **Ctrl + Alt + F8**, puis code technicien **propre à cette unité**. Le même mécanisme est prévu sur une box classique et sur la console avec application (bascule de terminal Linux/X11, sans changement du navigateur). Les claviers avec touche Fn peuvent nécessiter celle-ci pour produire F8.

La combinaison donne accès à l’authentification, jamais à une session native avant validation du code. Elle n’est pas un secret de sécurité : la protection repose sur le code individuel. Celui-ci n’est ni le mot de passe client ni la clé Wi-Fi. Il n’est pas affiché dans les paramètres destinés au client. Ne pas publier le kit technicien ni le mettre sur l’étiquette client.

Après authentification, systemd démarre l’outil natif `/usr/sbin/haos-cli` sur tty8. Ses commandes et son accès hôte sont ceux de HAOS, avec les droits administrateur correspondants. La session est temporaire : **10 minutes maximum**, limite gérée par l’hôte même si le module de maintenance s’arrête. Aucun redémarrage automatique de cette session. À sa fermeture, retour vers le terminal précédemment utilisé via `chvt` ; s’il est indisponible, revenir manuellement avec Ctrl+Alt+F1 (box classique) ou la touche F du terminal de l’app relevée pendant la recette console.

## Préparation individuelle

1. Installer le candidat sans l’activer (`enabled: false`). Le script `preflight.py`, exécutable ponctuellement dans l’image, donne en lecture seule l’identifiant machine du bus hôte et l’état des services tty8.
2. Sur le poste atelier : `python workshop.py --machine-id <32 caractères hexadécimaux> --output <nouveau-dossier-prive>`. Un nouveau dossier est obligatoire ; aucun fichier n’est écrasé.
3. Importer le seul `options-private.json` dans cette unité. Il contient l’identifiant machine et une empreinte PBKDF2-SHA256 salée (600 000 tours), jamais le code en clair. Le document `technicien-prive.txt` contenant le code de 24 chiffres est conservé dans le coffre de préparation de cette unité, hors du dépôt et des images communes.
4. Après préparation du profil de démarrage et redémarrage, activer le module et vérifier que tty8 est libre/réservé à cette fonction. Les instances getty/autovt/ha-cli de tty8 doivent être effectivement masquées ; le module le vérifie et refuse autrement pour éviter une console native concurrente. Le module refuse de remplacer une console déjà occupée ou graphique. Il n’ouvre jamais les périphériques `/dev/input` et ne lit que tty8 lorsque ce terminal est actif.
5. Tester le clavier USB directement sur la box et dans la console : bon et mauvais code, verrouillage, retour app, arrêt du module et expiration réelle de la session, redémarrage sans réouverture de session. Ce candidat est **désactivé par défaut et non qualifié matériellement**.
6. Réinitialisation/cession : désactiver, renouveler le code et remplacer le kit privé de cette unité. Une configuration copiée sur une autre machine est refusée.

## Portée des accès

Le module ne publie aucun serveur ni port. AppArmor interdit IPv4/IPv6 et les périphériques d’entrée bruts. Seuls `/dev/tty0` (état des terminaux) et `/dev/tty8` (authentification) sont mappés. Pas de PID hôte, API Supervisor/HA, socket Docker ou accès global aux périphériques. D-Bus hôte est nécessaire pour créer la session administrateur transitoire : c’est un droit sensible, à réserver à ce module maîtrisé. Les appels sont limités par le code au nom d’unité fixe, au programme natif HAOS, à tty8 et à une durée fixe ; aucun argument de commande libre ni secret dans les propriétés de l’unité.

Les échecs sont mémorisés : attente après chaque échec, puis blocage croissant dès 5 échecs, jusqu’à 10 minutes. Redémarrer le module ne remet pas le compteur à zéro ; un redémarrage hôte ne raccourcit pas le blocage. Aucun code saisi dans les journaux. La session ne reste pas déverrouillée après sa fermeture.

Le masquage HDMI et ce raccourci ne constituent pas du chiffrement ni une protection contre une personne capable de modifier physiquement le support de démarrage. Les accès série, les clés SSH techniques et la récupération hors ligne restent gérés séparément. Ne pas ajouter de clé SSH partagée ou de compte client administrateur pour ce parcours.
