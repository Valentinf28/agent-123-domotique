# Passerelle Lovelace sécurisée

## Résultat de la vérification

- Le tableau de bord distant répond avec `X-Frame-Options: SAMEORIGIN`. Une iframe
  pointant directement vers l’URL Nabu Casa est donc bloquée.
- Le frontend utilise REST et `/api/websocket`. Le protocole WebSocket exige un
  message `auth` contenant un jeton avant toute commande.
- L’API `external_auth` officielle cible les WebViews Android/iOS. Dans le
  navigateur, le portail fournit à la place un laissez-passer opaque de cinq
  minutes, conservé uniquement en mémoire. Le jeton technique HA reste côté
  serveur.
- Les cartes HACS sont des modules JavaScript chargés par le frontend. Elles
  restent compatibles uniquement si les ressources, API, médias et WebSockets
  sont servis par le même proxy.

## Architecture requise

Le portail ne doit jamais charger directement l’URL de la maison.

1. `/api/lovelace/session` vérifie la session du portail et l’appartenance à la maison.
2. Le serveur crée une session opaque, courte, liée à l’utilisateur et à la maison.
3. Le navigateur ouvre uniquement `/ma-maison/ha/lovelace/0?kiosk`, sur le même domaine.
4. La passerelle relaie les ressources statiques et les chemins autorisés.
5. Pour `/api/websocket`, elle authentifie le laissez-passer opaque, ouvre le WebSocket
   amont et injecte le jeton HA côté serveur pendant la phase `auth`.
6. Elle filtre les commandes WebSocket et HTTP par liste blanche.
7. Elle bloque toute navigation hors du tableau de bord autorisé.

## Routes autorisées

- `GET /ma-maison/ha/lovelace/0`
- ressources frontend nécessaires (`/frontend_latest/**`, `/local/**`,
  `/hacsfiles/**`, `/static/**`)
- médias signés nécessaires aux cartes
- `GET /api/websocket` via la passerelle avec filtrage des messages
- commandes Lovelace de lecture et services explicitement autorisés

Toutes les routes d’administration doivent répondre `404`, notamment :

- `/config/**`
- `/developer-tools/**`
- `/profile/**`
- `/auth/**`
- `/api/config/**`
- `/api/error/**`
- gestion des utilisateurs, intégrations, sauvegardes et réparations

## Configuration Home Assistant derrière un proxy traditionnel

À adapter à l’adresse privée exacte du proxy :

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 10.0.0.20
```

Ne pas utiliser une plage large. `use_x_frame_options` peut rester activé :
la réponse finale est servie sur le même domaine que le portail. Aucune origine
CORS supplémentaire n’est nécessaire pour une passerelle réellement same-origin.

## Déploiement et évolution multi-clients

La première version privée utilise la passerelle Worker de Sites. Pour passer en
production multi-clients, remplacer les deux variables d’environnement globales
par une table serveur `client -> maison -> secret`, résolue uniquement après
authentification. La session opaque doit contenir un identifiant de maison et la
passerelle doit le vérifier sur chaque requête HTTP et WebSocket. Les secrets HA
restent dans le coffre du service et ne sont jamais renvoyés au navigateur.
