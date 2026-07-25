#!/usr/bin/env python3
"""Agent minimal et sans dépendance pour Home Assistant OS."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/agent-state.json")
SUPERVISOR_API = "http://supervisor/core/api"


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


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> dict[str, Any] | list[Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
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
    return {
        "haVersion": str(config.get("version", "")),
        "inventoryCount": len(states),
        "availableCount": available,
    }


def heartbeat(portal_url: str, agent_token: str, summary: dict[str, Any]) -> int:
    result = request_json(
        f"{portal_url}/agent/heartbeat",
        method="POST",
        token=agent_token,
        payload=summary,
    )
    if isinstance(result, dict):
        return max(15, min(300, int(result.get("nextHeartbeatSeconds", 30))))
    return 30


def main() -> None:
    options = read_json(OPTIONS_PATH, {})
    portal_url = str(options.get("portal_url", "")).rstrip("/")
    enrollment_code = str(options.get("enrollment_code", "")).strip().upper()
    interval = max(15, min(300, int(options.get("heartbeat_seconds", 30))))
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not portal_url or not enrollment_code or not supervisor_token:
        raise SystemExit("Configuration incomplète : URL, code et accès Home Assistant requis")

    state = read_json(STATE_PATH, {})
    while True:
        try:
            if not state.get("token"):
                state = enroll(portal_url, enrollment_code)
            summary = home_assistant_summary(supervisor_token)
            interval = heartbeat(portal_url, str(state["token"]), summary)
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
