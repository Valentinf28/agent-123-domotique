#!/usr/bin/env python3
"""Agent minimal et sans dépendance pour Home Assistant OS."""

from __future__ import annotations

import json
import base64
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import websocket

HA_TUNNELS: dict[str, websocket.WebSocket] = {}

OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/agent-state.json")
SUPERVISOR_API = "http://supervisor/core/api"
HOME_ASSISTANT_FRONTEND = "http://homeassistant:8123"


def log(message: str) -> None:
    print(f"[agent-123] {message}", flush=True)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(STATE_PATH)


def home_assistant_ws_command(
    supervisor_token: str,
    command: dict[str, Any],
    timeout: int = 20,
) -> dict[str, Any]:
    socket = websocket.create_connection("ws://supervisor/core/websocket", timeout=timeout)
    try:
        auth_required = json.loads(socket.recv())
        if not isinstance(auth_required, dict) or auth_required.get("type") != "auth_required":
            raise RuntimeError("Authentification WebSocket Home Assistant inattendue")
        socket.send(json.dumps({"type": "auth", "access_token": supervisor_token}))
        auth_result = json.loads(socket.recv())
        if not isinstance(auth_result, dict) or auth_result.get("type") != "auth_ok":
            raise RuntimeError("Authentification WebSocket Home Assistant refusée")
        request_id = int(time.time() * 1000) % 2_000_000_000
        socket.send(json.dumps({"id": request_id, **command}))
        while True:
            response = json.loads(socket.recv())
            if not isinstance(response, dict) or response.get("id") != request_id:
                continue
            if response.get("type") != "result" or not response.get("success"):
                error = response.get("error")
                raise RuntimeError(f"Commande Home Assistant refusée ({error})")
            result = response.get("result")
            return result if isinstance(result, dict) else {"result": result}
    finally:
        socket.close()


def apply_dashboard(
    supervisor_token: str,
    dashboard: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    # Le portail ne doit jamais remplacer le tableau de bord principal du client.
    # La génération automatique sera réintroduite sur un tableau dédié.
    return False


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> dict[str, Any] | list[Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": "Agent-123-Domotique/0.5.1",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def enroll(portal_url: str, code: str) -> dict[str, Any]:
    result = request_json(
        f"{portal_url}/agent/enroll",
        method="POST",
        payload={"code": code, "label": "Box Home Assistant"},
    )
    if not isinstance(result, dict) or not result.get("token"):
        raise RuntimeError("Réponse d'enrôlement invalide")
    state = {"agent_id": result["agentId"], "token": result["token"]}
    write_state(state)
    log("Box associée au portail")
    return state


def home_assistant_summary(supervisor_token: str) -> dict[str, Any]:
    config = request_json(f"{SUPERVISOR_API}/config", token=supervisor_token)
    states = request_json(f"{SUPERVISOR_API}/states", token=supervisor_token)
    if not isinstance(config, dict) or not isinstance(states, list):
        raise RuntimeError("Réponse Home Assistant invalide")
    available = sum(
        1 for state in states
        if isinstance(state, dict) and state.get("state") not in {"unavailable", "unknown"}
    )
    inventory = []
    for state in states[:1000]:
        if not isinstance(state, dict):
            continue
        entity_id = str(state.get("entity_id", ""))
        attributes = state.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        inventory.append({
            "entityId": entity_id,
            "name": str(attributes.get("friendly_name", entity_id)),
            "domain": entity_id.split(".", 1)[0] if "." in entity_id else "",
            "state": str(state.get("state", "")),
            "deviceClass": attributes.get("device_class"),
        })
    return {
        "haVersion": str(config.get("version", "")),
        "inventoryCount": len(states),
        "availableCount": available,
        "inventory": inventory,
    }


def relay_command(
    supervisor_token: str,
    message: dict[str, Any],
    relay_send=None,
) -> dict[str, Any]:
    command_id = str(message.get("id", ""))
    action = str(message.get("action", ""))
    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    try:
        if action == "ha.states":
            result = request_json(f"{SUPERVISOR_API}/states", token=supervisor_token)
        elif action == "ha.config":
            result = request_json(f"{SUPERVISOR_API}/config", token=supervisor_token)
        elif action == "ha.services.call":
            domain = str(payload.get("domain", "")).strip()
            service = str(payload.get("service", "")).strip()
            if not domain.replace("_", "").isalnum() or not service.replace("_", "").isalnum():
                raise ValueError("Service Home Assistant invalide")
            service_data = payload.get("data")
            if not isinstance(service_data, dict):
                service_data = {}
            result = request_json(
                f"{SUPERVISOR_API}/services/{domain}/{service}",
                method="POST",
                token=supervisor_token,
                payload=service_data,
                timeout=60,
            )
        elif action == "ha.history":
            start = urllib.parse.quote(str(payload.get("start", "")), safe=":TZ+-")
            entity_id = urllib.parse.quote(str(payload.get("entityId", "")), safe="._")
            if not start or not entity_id:
                raise ValueError("Période ou entité manquante")
            result = request_json(
                f"{SUPERVISOR_API}/history/period/{start}?filter_entity_id={entity_id}&minimal_response",
                token=supervisor_token,
            )
        elif action == "ha.proxy":
            method = str(payload.get("method", "GET")).upper()
            path = str(payload.get("path", "/"))
            if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                raise ValueError("Méthode refusée")
            if not path.startswith("/") or path.startswith((
                "/config", "/developer-tools", "/profile", "/hassio", "/supervisor",
                "/api/config", "/api/error", "/api/onboarding", "/api/repairs",
            )):
                raise ValueError("Chemin refusé")
            body = base64.b64decode(str(payload.get("body", "")))
            forwarded_headers = payload.get("headers")
            if not isinstance(forwarded_headers, dict):
                forwarded_headers = {}
            headers = {
                "Authorization": f"Bearer {supervisor_token}",
                **{
                    str(key): str(value) for key, value in forwarded_headers.items()
                    if str(key).lower() in {"accept", "content-type", "if-none-match", "if-modified-since"}
                },
            }
            request = urllib.request.Request(
                f"{HOME_ASSISTANT_FRONTEND}{path}",
                data=body if body or method not in {"GET", "DELETE"} else None,
                headers=headers,
                method=method,
            )
            try:
                response = urllib.request.urlopen(request, timeout=25)
            except urllib.error.HTTPError as error:
                response = error
            raw = response.read()
            result = {
                "status": response.status,
                "headers": {
                    key: value for key, value in response.headers.items()
                    if key.lower() in {"content-type", "cache-control", "etag", "last-modified"}
                },
                "body": base64.b64encode(raw).decode(),
            }
        elif action == "ha.ws.open":
            tunnel_id = str(payload.get("tunnelId", ""))
            if not tunnel_id or relay_send is None:
                raise ValueError("Tunnel invalide")
            upstream = websocket.create_connection(
                "ws://supervisor/core/websocket",
                timeout=30,
            )
            # The connection timeout is useful only while opening the socket.
            # Lovelace subscriptions are long-lived and can remain silent for
            # extended periods without the tunnel being disconnected.
            upstream.settimeout(None)
            HA_TUNNELS[tunnel_id] = upstream

            def forward() -> None:
                try:
                    while True:
                        raw = upstream.recv()
                        decoded = json.loads(raw)
                        if isinstance(decoded, dict) and decoded.get("type") == "auth_required":
                            upstream.send(json.dumps({
                                "type": "auth",
                                "access_token": supervisor_token,
                            }))
                            continue
                        relay_send({
                            "type": "tunnel.event",
                            "tunnelId": tunnel_id,
                            "data": raw,
                        })
                except Exception as error:
                    log(f"Tunnel Lovelace {tunnel_id[:8]} fermé ({error})")
                    relay_send({"type": "tunnel.closed", "tunnelId": tunnel_id})
                finally:
                    HA_TUNNELS.pop(tunnel_id, None)
                    try:
                        upstream.close()
                    except Exception:
                        pass

            threading.Thread(target=forward, daemon=True).start()
            result = {"opened": True}
        elif action == "ha.ws.send":
            tunnel_id = str(payload.get("tunnelId", ""))
            upstream = HA_TUNNELS.get(tunnel_id)
            if not upstream:
                raise ValueError("Tunnel fermé")
            upstream.send(str(payload.get("data", "")))
            result = {"sent": True}
        elif action == "ha.ws.close":
            tunnel_id = str(payload.get("tunnelId", ""))
            upstream = HA_TUNNELS.pop(tunnel_id, None)
            if upstream:
                upstream.close()
            result = {"closed": True}
        else:
            raise ValueError("Commande non autorisée")
        return {"type": "command.result", "id": command_id, "ok": True, "result": result}
    except Exception as error:
        return {
            "type": "command.result",
            "id": command_id,
            "ok": False,
            "error": str(error)[:240],
        }


def relay_forever(relay_url: str, house_id: str, relay_token: str, supervisor_token: str) -> None:
    delay = 2
    while True:
        socket: websocket.WebSocket | None = None
        try:
            socket = websocket.create_connection(relay_url, timeout=30)
            send_lock = threading.Lock()

            def relay_send(payload: dict[str, Any]) -> None:
                with send_lock:
                    socket.send(json.dumps(payload))

            relay_send({
                "type": "authenticate",
                "houseId": house_id,
                "token": relay_token,
            })
            reply = json.loads(socket.recv())
            if reply.get("type") != "authenticated":
                raise RuntimeError("Authentification du relais refusée")
            log("Liaison sécurisée VPS active")
            delay = 2
            socket.settimeout(45)
            while True:
                try:
                    message = json.loads(socket.recv())
                except websocket.WebSocketTimeoutException:
                    socket.ping()
                    continue
                if message.get("type") == "command":
                    relay_send(relay_command(supervisor_token, message, relay_send))
        except Exception as error:
            log(f"Relais indisponible ({error}), reconnexion dans {delay}s")
        finally:
            if socket:
                try:
                    socket.close()
                except Exception:
                    pass
        time.sleep(delay)
        delay = min(delay * 2, 60)


def heartbeat(portal_url: str, agent_token: str, summary: dict[str, Any]) -> dict[str, Any]:
    result = request_json(
        f"{portal_url}/agent/heartbeat",
        method="POST",
        token=agent_token,
        payload=summary,
    )
    if not isinstance(result, dict):
        return {"nextHeartbeatSeconds": 30}
    return result


def main() -> None:
    options = read_json(OPTIONS_PATH, {})
    portal_url = str(options.get("portal_url", "")).rstrip("/")
    enrollment_code = str(options.get("enrollment_code", "")).strip().upper()
    interval = max(15, min(300, int(options.get("heartbeat_seconds", 30))))
    relay_url = str(options.get("relay_url", "")).strip()
    relay_house_id = str(options.get("relay_house_id", "")).strip()
    relay_token = str(options.get("relay_token", "")).strip()
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        raise SystemExit("Accès interne à Home Assistant indisponible")
    if not enrollment_code and not (relay_url and relay_house_id and relay_token):
        raise SystemExit("Configuration incomplète : code d'installation ou liaison VPS requis")

    state = read_json(STATE_PATH, {})
    if relay_url and relay_house_id and relay_token:
        threading.Thread(
            target=relay_forever,
            args=(relay_url, relay_house_id, relay_token, supervisor_token),
            daemon=True,
        ).start()
    else:
        log("Liaison VPS non configurée")
    if not enrollment_code:
        log("Portail technicien non enrôlé ; liaison VPS uniquement")
        while True:
            time.sleep(300)
    while True:
        try:
            if not state.get("token"):
                state = enroll(portal_url, enrollment_code)
            summary = home_assistant_summary(supervisor_token)
            heartbeat_result = heartbeat(portal_url, str(state["token"]), summary)
            interval = max(15, min(300, int(heartbeat_result.get("nextHeartbeatSeconds", 30))))
            dashboard = heartbeat_result.get("dashboard")
            if isinstance(dashboard, dict):
                apply_dashboard(supervisor_token, dashboard, state)
            log(
                f"Connecté · Home Assistant {summary['haVersion']} · "
                f"{summary['inventoryCount']} entités"
            )
        except urllib.error.HTTPError as error:
            if error.code == 401 and state.get("token"):
                log("Identité de box refusée ; nouvel enrôlement requis")
                state = {}
                try:
                    STATE_PATH.unlink()
                except FileNotFoundError:
                    pass
            else:
                log(f"Portail indisponible (HTTP {error.code}), nouvelle tentative")
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as error:
            log(f"Connexion impossible ({error}), nouvelle tentative")
        time.sleep(interval)


if __name__ == "__main__":
    main()
