# Agent 1.2.3 Domotique

Application Home Assistant OS permettant de rattacher une box au portail
technicien 1.2.3 Domotique sans exposer les identifiants Home Assistant.

## Installation

1. Dans Home Assistant, ouvrir **Paramètres > Applications > Boutique**.
2. Ajouter le dépôt `https://github.com/Valentinf28/agent-123-domotique`.
3. Installer **Agent 1.2.3 Domotique**.
4. Dans le portail, passer en mode Installateur, ouvrir **Installation** puis
   sélectionner **Associer la box**.
5. Reporter le code temporaire dans la configuration de l'agent.
6. Démarrer l'agent et vérifier que le portail affiche la box comme connectée.

Le code expire après 30 minutes et ne peut être utilisé qu'une seule fois.

## Données transmises

L’agent transmet la version, l’inventaire utile et les états nécessaires au
portail. Il récupère aussi une file de commandes autorisées et les exécute
localement. Le jeton interne Home Assistant reste dans la box.
