# Préparation HDMI — candidat 0.2.0

Masque la console HAOS en HDMI sur une box classique ; une console équipée de l’app continue d’afficher celle-ci. Pas de navigateur ni d’animation supplémentaire sur les box sans écran. Les journaux, Supervisor, Home Assistant et le réseau restent fonctionnels.

Le profil `hdmi-maintenance-v2` conserve les paramètres root/disque et la console série, réduit les messages de démarrage et masque les modèles getty/autovt/ha-cli des terminaux graphiques ordinaires. L’accès technique passe alors par le module `labox_maintenance`, sa console réservée tty8 et son code individuel. Les messages du firmware/bootloader, antérieurs à Linux, ne sont pas contrôlés par ce profil.

## Atelier : méthode recommandée hors ligne

Travailler sur la partition de démarrage de l’unité sélectionnée, après sa préparation. L’outil ne sait modifier que `cmdline.txt`. Aucun changement de partition, noyau ou firmware.

1. Identifier la carte, la version HAOS et le support physique. Les formats initiaux pris en charge sont ODROID M1S, M1 et N2 sous HAOS 18.3. Le précédent masquage sur M1S a été observé réellement sur la console ; ce nouveau profil et la maintenance tty8 nécessitent une recette physique.
2. Provisionner le kit de maintenance avant de masquer la console habituelle ; conserver ce kit privé et valider un accès de secours atelier SSH ou une récupération hors ligne. Le module de maintenance refusera d’ouvrir tty8 avant le premier redémarrage avec les masques getty appliqués.
3. Monter la partition en lecture seule et préparer un plan : `python boot.py plan --boot /chemin/boot --machine odroid-m1s --haos 18.3`. Le résultat ne contient pas les paramètres de démarrage ni leurs éventuels secrets.
4. Après examen du plan, remonter cette seule partition en écriture et exécuter `python boot.py apply --boot /chemin/boot --backups /chemin/prive/sauvegardes --machine odroid-m1s --haos 18.3 --expected-sha256 <beforeSha256> --device-id <identifiant-support>`. Le dossier de sauvegarde doit exister et être situé hors de la partition de démarrage.
5. Archiver la sauvegarde privée et son reçu avec le dossier de cette unité. Démontage propre puis redémarrage manuel.
6. Contrôler HDMI, retour de l’app le cas échéant, réseau, accès technique par code, expiration et redémarrage. Ne pas livrer si l’accès de secours n’a pas été vérifié.

Restauration : `python boot.py restore --boot /chemin/boot --backup /chemin/hdmi-… --expected-sha256 <afterSha256> --device-id <même-identifiant-support>`. Refus si le contenu courant a changé ou si l’empreinte du reçu et celle de la sauvegarde ne concordent pas. Jamais de reconstruction à partir d’un fichier générique.

## Outil temporaire sur une unité déjà démarrée

Le module HAOS fourni est une alternative atelier. Il reste manuel et ne peut pas démarrer automatiquement. Son mode initial `plan` monte la partition en lecture seule. Le périphérique et le PARTUUID doivent être fournis explicitement et correspondre à une partition FAT étiquetée `hassos-boot`. Aucune détection automatique susceptible de choisir une autre carte.

HAOS impose un accès temporaire aux périphériques et SYS_ADMIN pour monter sa propre partition de démarrage. L’outil ne bénéficie ni du réseau dans son processus de travail, ni du PID hôte, ni d’une API HA/Supervisor. AppArmor limite les montages à une partition FAT sur `/tmp/labox-boot`. Ces droits nécessitent une intervention atelier explicite : ils ne font pas partie des droits permanents de l’agent.

Après sauvegarde et écriture, rétablir la protection et désinstaller l’outil avant le redémarrage. Aucun redémarrage automatique n’est déclenché. Les sauvegardes sont conservées dans `/share/labox-boot-backups/` et doivent également être récupérées hors de la box. PARTUUID identifie une partition ; sur une image clonée il ne prouve pas, seul, l’identité physique de l’unité : conserver le reçu dans le dossier atelier de la bonne box.

## Après une mise à jour HAOS

Exécuter un audit du `cmdline.txt` et contrôler les paramètres effectifs du nouveau démarrage. Une nouvelle version HAOS ou un autre format de boot est refusé en écriture tant qu’il n’a pas été qualifié. Aucun rétablissement silencieux de paramètres après mise à jour. Revalider aussi `/usr/sbin/haos-cli`, les raccourcis VT, le profil AppArmor et le retour vers l’app.

Références : [console et diagnostic HAOS](https://contributors.home-assistant.io/os/operating-system/debugging/), [service CLI HAOS 18.3](https://github.com/home-assistant/operating-system/blob/18.3/buildroot-external/rootfs-overlay/usr/lib/systemd/system/ha-cli%40.service), [paramètres systemd](https://www.freedesktop.org/software/systemd/man/latest/kernel-command-line.html).
