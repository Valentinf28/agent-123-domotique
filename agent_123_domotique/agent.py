#!/usr/bin/env python3
"""Agent minimal et sans dépendance pour Home Assistant OS."""

from __future__ import annotations

import json
import base64
import math
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import websocket

HA_TUNNELS: dict[str, websocket.WebSocket] = {}

OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/agent-state.json")
SUPERVISOR_API = "http://supervisor/core/api"
HOME_ASSISTANT_FRONTEND = "http://homeassistant:8123"
FULL_INVENTORY_SECONDS = 60
SOLAR_FORECAST_REFRESH_SECONDS = 15 * 60
SOLAR_FORECAST_PREFIX = "sensor.1_2_3_home_solar_forecast_"
SOLAR_FORECAST_CACHE: list[dict[str, Any]] = []
SOLAR_FORECAST_FETCHED_AT = 0.0
FAST_ENTITY_PREFIXES = (
    "sensor.inverter_",
    "sensor.onduleur_",
    "sensor.shellyem3_",
    "sensor.1_2_3_home_",
    "sensor.filtration_piscine_",
    "input_boolean.demo_",
    "input_boolean.chauffe_eau_",
    "input_number.demo_",
    "input_number.chauffe_eau_",
    "input_select.demo_",
    "input_select.chauffe_eau_",
)
SHELLY_DAILY_ENERGY_BINDINGS = (
    (
        "sensor.shellyem3_483fdac38616_channel_b_energy",
        "sensor.1_2_3_home_today_consumption",
        "Consommation maison aujourd'hui",
    ),
    (
        "sensor.shellyem3_483fdac38616_channel_c_energy",
        "sensor.1_2_3_home_today_energy_import",
        "Énergie achetée aujourd'hui",
    ),
    (
        "sensor.shellyem3_483fdac38616_channel_c_energy_returned",
        "sensor.1_2_3_home_today_energy_export",
        "Énergie injectée aujourd'hui",
    ),
)
PERIOD_ENERGY_BINDINGS = (
    ("sensor.onduleur_total_production", "production", "Production"),
    ("sensor.shellyem3_483fdac38616_channel_b_energy", "consumption", "Consommation"),
    ("sensor.shellyem3_483fdac38616_channel_c_energy", "import", "Énergie achetée"),
    ("sensor.shellyem3_483fdac38616_channel_c_energy_returned", "export", "Énergie injectée"),
)


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
        "User-Agent": "Agent-123-Domotique/0.5.17",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def daily_energy_delta(current_state: str, history: Any) -> float | None:
    try:
        current = float(current_state)
    except (TypeError, ValueError):
        return None
    if not isinstance(history, list):
        return None
    series = history[0] if history and isinstance(history[0], list) else history
    baseline = None
    for row in series:
        if not isinstance(row, dict):
            continue
        try:
            baseline = float(row.get("state"))
            break
        except (TypeError, ValueError):
            continue
    if baseline is None or current < baseline:
        return None
    return round(current - baseline, 4)


def shelly_daily_energy_inventory(
    supervisor_token: str,
    config: dict[str, Any],
    states: list[Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    try:
        timezone_name = str(config.get("time_zone", "Europe/Paris"))
        try:
            local_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            local_timezone = timezone.utc
        current_time = now.astimezone(local_timezone) if now else datetime.now(local_timezone)
        day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        encoded_start = urllib.parse.quote(day_start.isoformat(), safe=":TZ+-")
        by_entity_id = {
            str(item.get("entity_id")): item
            for item in states
            if isinstance(item, dict) and item.get("entity_id")
        }
        entries = []
        for source_entity_id, target_entity_id, name in SHELLY_DAILY_ENERGY_BINDINGS:
            current = by_entity_id.get(source_entity_id)
            if not current:
                continue
            encoded_entity_id = urllib.parse.quote(source_entity_id, safe="._")
            history = request_json(
                f"{SUPERVISOR_API}/history/period/{encoded_start}"
                f"?filter_entity_id={encoded_entity_id}&minimal_response",
                token=supervisor_token,
            )
            delta = daily_energy_delta(str(current.get("state", "")), history)
            if delta is None:
                continue
            entries.append({
                "entityId": target_entity_id,
                "name": name,
                "domain": "sensor",
                "state": str(delta),
                "deviceClass": "energy",
            })
        return entries
    except Exception as error:
        log(f"Compteurs journaliers Shelly indisponibles ({error})")
        return []


def energy_period_starts(current_time: datetime) -> dict[str, datetime]:
    return {
        "daily": current_time.replace(hour=0, minute=0, second=0, microsecond=0),
        "monthly": current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        "yearly": current_time.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
    }


def period_energy_inventory(
    supervisor_token: str,
    config: dict[str, Any],
    states: list[Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Publie les mêmes cumuls jour/mois/année pour le portail et l'app."""
    try:
        timezone_name = str(config.get("time_zone", "Europe/Paris"))
        try:
            local_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            local_timezone = timezone.utc
        current_time = now.astimezone(local_timezone) if now else datetime.now(local_timezone)
        starts = energy_period_starts(current_time)
        by_entity_id = {
            str(item.get("entity_id")): item
            for item in states
            if isinstance(item, dict) and item.get("entity_id")
        }
        entries: list[dict[str, Any]] = []
        for source_entity_id, metric, label in PERIOD_ENERGY_BINDINGS:
            current = by_entity_id.get(source_entity_id)
            if not current:
                continue
            encoded_entity_id = urllib.parse.quote(source_entity_id, safe="._")
            for period, period_start in starts.items():
                # Les compteurs journaliers Deye/Shelly natifs restent prioritaires.
                # Ce cumul est leur secours et la référence commune mois/année.
                encoded_start = urllib.parse.quote(period_start.isoformat(), safe=":TZ+-")
                history = request_json(
                    f"{SUPERVISOR_API}/history/period/{encoded_start}"
                    f"?filter_entity_id={encoded_entity_id}&minimal_response&no_attributes",
                    token=supervisor_token,
                )
                delta = daily_energy_delta(str(current.get("state", "")), history)
                if delta is None:
                    continue
                entries.append({
                    "entityId": f"sensor.1_2_3_home_{period}_{metric}",
                    "name": f"{label} {period}",
                    "domain": "sensor",
                    "state": str(delta),
                    "deviceClass": "energy",
                })
        return entries
    except Exception as error:
        log(f"Cumuls énergétiques indisponibles ({error})")
        return []


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


def home_assistant_summary(
    supervisor_token: str,
    *,
    full_inventory: bool = True,
) -> dict[str, Any]:
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
        if not full_inventory and not entity_id.startswith(FAST_ENTITY_PREFIXES):
            continue
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
    if full_inventory:
        inventory.extend(shelly_daily_energy_inventory(
            supervisor_token,
            config,
            states,
        ))
        inventory.extend(period_energy_inventory(
            supervisor_token,
            config,
            states,
        ))
        inventory.extend(solar_forecast_inventory(supervisor_token, states))
    return {
        "haVersion": str(config.get("version", "")),
        "inventoryCount": len(states),
        "inventoryMode": "full" if full_inventory else "delta",
        "availableCount": available,
        "inventory": inventory,
    }


def _forecast_energy_wh(state: dict[str, Any] | None) -> float | None:
    if not state:
        return None
    try:
        value = max(0.0, float(state.get("state", "")))
    except (TypeError, ValueError):
        return None
    attributes = state.get("attributes")
    unit = str(attributes.get("unit_of_measurement", "") if isinstance(attributes, dict) else "")
    if unit.lower() == "wh":
        return value
    # Forecast.Solar exposes its aggregate energy sensors in kWh.
    return value * 1000


def _forecast_peak_hour(
    state: dict[str, Any] | None,
    fallback: float = 12.5,
) -> float:
    if not state:
        return fallback
    raw = str(state.get("state", "")).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo:
            parsed = parsed.astimezone()
        return parsed.hour + parsed.minute / 60
    except ValueError:
        return fallback


def _hourly_shape(starts_at: datetime, peak_hour: float) -> float:
    local = starts_at.astimezone()
    hour = local.hour + 0.5
    if hour < 5 or hour > 21:
        return 0.0
    return math.exp(-0.5 * ((hour - peak_hour) / 3.4) ** 2)


def _distribute_energy(
    entries: list[float],
    slots: list[datetime],
    start: int,
    end: int,
    total_wh: float,
    peak_hour: float,
    fixed: dict[int, float] | None = None,
) -> None:
    fixed = fixed or {}
    for index, value in fixed.items():
        if start <= index < end:
            entries[index] = max(0.0, value)
    residual = max(
        0.0,
        total_wh - sum(entries[index] for index in fixed if start <= index < end),
    )
    flexible = [index for index in range(start, end) if index not in fixed]
    weights = [_hourly_shape(slots[index], peak_hour) for index in flexible]
    weight_total = sum(weights)
    if not flexible:
        return
    if weight_total <= 0:
        weights = [1.0] * len(flexible)
        weight_total = float(len(flexible))
    for index, weight in zip(flexible, weights):
        entries[index] = residual * weight / weight_total


def _distribute_daily_energy(
    entries: list[float],
    slots: list[datetime],
    target_date,
    total_wh: float,
    peak_hour: float,
    *,
    remaining_only: bool,
) -> None:
    indexes = [
        index
        for index, slot in enumerate(slots)
        if slot.astimezone().date() == target_date
    ]
    if not indexes or total_wh <= 0:
        return
    weights = [_hourly_shape(slots[index], peak_hour) for index in indexes]
    if remaining_only:
        weight_total = sum(weights)
    else:
        start = slots[indexes[0]].astimezone().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        weight_total = sum(
            _hourly_shape(start + timedelta(hours=hour), peak_hour)
            for hour in range(24)
        )
    if weight_total <= 0:
        return
    for index, weight in zip(indexes, weights):
        entries[index] = total_wh * weight / weight_total


def fallback_solar_forecast_inventory(
    states: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build a 24-hour curve from aggregate solar forecast sensors.

    Home Assistant 2026.7.2 can reject ``energy/solar_forecast`` even though
    ordinary forecast sensors are healthy. This fallback accepts Forecast.Solar
    and Open-Meteo, without calling the weather provider again.
    """
    state_by_id = {
        str(state.get("entity_id", "")): state
        for state in states
        if isinstance(state, dict)
    }

    def first_state(*entity_ids: str) -> dict[str, Any] | None:
        for entity_id in entity_ids:
            candidate = state_by_id.get(entity_id)
            if candidate and str(candidate.get("state", "")) not in {
                "unavailable",
                "unknown",
                "",
            }:
                return candidate
        return None

    next_12 = _forecast_energy_wh(state_by_id.get("sensor.energy_production_next_12hours"))
    next_24 = _forecast_energy_wh(state_by_id.get("sensor.energy_production_next_24hours"))
    current_hour = _forecast_energy_wh(first_state(
        "sensor.energy_current_hour",
        "sensor.maison_energy_current_hour",
    ))
    next_hour = _forecast_energy_wh(first_state(
        "sensor.energy_next_hour",
        "sensor.maison_energy_next_hour",
    ))
    today_remaining = _forecast_energy_wh(
        first_state(
            "sensor.energy_production_today_remaining",
            "sensor.maison_energy_production_today_remaining",
        )
    )
    tomorrow = _forecast_energy_wh(
        first_state(
            "sensor.energy_production_tomorrow",
            "sensor.maison_energy_production_tomorrow",
        )
    )
    if all(
        value is None
        for value in (
            next_12,
            next_24,
            current_hour,
            next_hour,
            today_remaining,
            tomorrow,
        )
    ):
        return []

    reference = now or datetime.now().astimezone()
    if reference.tzinfo is None:
        reference = reference.astimezone()
    first_slot = reference.replace(minute=0, second=0, microsecond=0)
    slots = [first_slot + timedelta(hours=index) for index in range(24)]
    values = [0.0] * len(slots)

    peak_today = _forecast_peak_hour(
        first_state(
            "sensor.power_highest_peak_time_today",
            "sensor.maison_power_highest_peak_time_today",
        ),
    )
    peak_tomorrow = _forecast_peak_hour(
        first_state(
            "sensor.power_highest_peak_time_tomorrow",
            "sensor.maison_power_highest_peak_time_tomorrow",
        ),
        peak_today,
    )
    if next_12 is not None or next_24 is not None:
        next_12 = max(0.0, next_12 or 0.0)
        next_24 = max(next_12, next_24 if next_24 is not None else next_12)
        fixed = {}
        if current_hour is not None:
            fixed[0] = current_hour
        if next_hour is not None:
            fixed[1] = next_hour
        _distribute_energy(values, slots, 0, 12, next_12, peak_today, fixed)
        _distribute_energy(
            values,
            slots,
            12,
            24,
            max(0.0, next_24 - next_12),
            peak_tomorrow,
        )
    else:
        today = reference.astimezone().date()
        _distribute_daily_energy(
            values,
            slots,
            today,
            max(0.0, today_remaining or 0.0),
            peak_today,
            remaining_only=True,
        )
        _distribute_daily_energy(
            values,
            slots,
            today + timedelta(days=1),
            max(0.0, tomorrow or 0.0),
            peak_tomorrow,
            remaining_only=False,
        )

    return [
        {
            "entityId": f"{SOLAR_FORECAST_PREFIX}{index:02d}",
            "name": f"Prévision solaire {slot.isoformat()}",
            "domain": "sensor",
            "state": str(round(values[index])),
            "deviceClass": "energy",
        }
        for index, slot in enumerate(slots)
    ]


def solar_forecast_inventory(
    supervisor_token: str,
    states: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose Home Assistant's solar forecast as ordinary, short-lived inventory rows."""
    global SOLAR_FORECAST_CACHE, SOLAR_FORECAST_FETCHED_AT
    now = time.monotonic()
    if (
        SOLAR_FORECAST_CACHE and
        now - SOLAR_FORECAST_FETCHED_AT < SOLAR_FORECAST_REFRESH_SECONDS
    ):
        return SOLAR_FORECAST_CACHE
    try:
        response = home_assistant_ws_command(
            supervisor_token,
            {"type": "energy/solar_forecast"},
        )
        sources = response.get("result") if set(response) == {"result"} else response
        if not isinstance(sources, dict):
            sources = {}
        combined: dict[str, float] = {}
        for source in sources.values():
            if not isinstance(source, dict):
                continue
            wh_hours = source.get("wh_hours")
            if not isinstance(wh_hours, dict):
                continue
            for timestamp, raw_value in wh_hours.items():
                try:
                    value = max(0.0, float(raw_value))
                except (TypeError, ValueError):
                    continue
                combined[str(timestamp)] = combined.get(str(timestamp), 0.0) + value
        entries = []
        for index, (timestamp, watt_hours) in enumerate(sorted(combined.items())[:72]):
            entries.append({
                "entityId": f"{SOLAR_FORECAST_PREFIX}{index:02d}",
                "name": f"Prévision solaire {timestamp}",
                "domain": "sensor",
                "state": str(round(watt_hours)),
                "deviceClass": "energy",
            })
        if not entries:
            entries = fallback_solar_forecast_inventory(states)
            if entries:
                log("Prévision solaire reconstruite depuis les capteurs disponibles")
        SOLAR_FORECAST_CACHE = entries
        SOLAR_FORECAST_FETCHED_AT = now
        if entries:
            log(f"Prévision solaire reçue · {len(entries)} créneaux")
        return entries
    except Exception as error:
        SOLAR_FORECAST_FETCHED_AT = now
        fallback = fallback_solar_forecast_inventory(states)
        if fallback:
            SOLAR_FORECAST_CACHE = fallback
            log(
                "Prévision solaire reconstruite depuis les capteurs disponibles "
                f"(courbe Home Assistant indisponible : {error})"
            )
            return fallback
        log(f"Prévision solaire indisponible ({error})")
        return SOLAR_FORECAST_CACHE


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
        elif action == "ha.automation.create":
            name = str(payload.get("name", "")).strip()
            trigger_time = str(payload.get("time", "")).strip()
            entity_id = str(payload.get("entityId", "")).strip()
            domain = str(payload.get("domain", "")).strip()
            service = str(payload.get("service", "")).strip()
            entity_parts = entity_id.split(".", 1)
            allowed_services = {
                "light": {"turn_on", "turn_off"},
                "switch": {"turn_on", "turn_off"},
                "fan": {"turn_on", "turn_off"},
                "climate": {"turn_on", "turn_off"},
                "lock": {"lock", "unlock"},
                "cover": {"open_cover", "close_cover"},
                "input_boolean": {"turn_on", "turn_off"},
            }
            if len(name) < 3 or len(name) > 80:
                raise ValueError("Nom d’automatisation invalide")
            try:
                datetime.strptime(trigger_time, "%H:%M")
            except ValueError as error:
                raise ValueError("Horaire invalide") from error
            if (
                len(entity_parts) != 2
                or entity_parts[0] != domain
                or not all(part.replace("_", "").isalnum() for part in entity_parts)
                or service not in allowed_services.get(domain, set())
            ):
                raise ValueError("Action d’automatisation refusée")
            automation_id = (
                f"ma_maison_{int(time.time())}_{secrets.token_hex(3)}"
            )
            result = request_json(
                f"{SUPERVISOR_API}/config/automation/config/{automation_id}",
                method="POST",
                token=supervisor_token,
                payload={
                    "id": automation_id,
                    "alias": f"1.2.3 Home · {name}",
                    "description": "Créée depuis le portail Ma Maison",
                    "trigger": [{
                        "platform": "time",
                        "at": f"{trigger_time}:00",
                    }],
                    "condition": [],
                    "action": [{
                        "service": f"{domain}.{service}",
                        "target": {"entity_id": entity_id},
                    }],
                    "mode": "single",
                },
                timeout=60,
            )
            request_json(
                f"{SUPERVISOR_API}/services/automation/reload",
                method="POST",
                token=supervisor_token,
                payload={},
                timeout=60,
            )
        elif action == "ha.automation.delete":
            entity_id = str(payload.get("entityId", "")).strip()
            parts = entity_id.split(".", 1)
            if (
                len(parts) != 2
                or parts[0] != "automation"
                or not all(part.replace("_", "").isalnum() for part in parts)
            ):
                raise ValueError("Automatisation invalide")
            listed = home_assistant_ws_command(
                supervisor_token,
                {"type": "config/automation/list"},
            ).get("result", [])
            automation = next(
                (
                    item for item in listed
                    if isinstance(item, dict)
                    and item.get("entity_id") == entity_id
                    and str(item.get("alias", "")).startswith("1.2.3 Home")
                ),
                None,
            )
            automation_id = str(automation.get("id", "")) if automation else ""
            if not automation_id or not all(
                char.isalnum() or char in {"_", "-"}
                for char in automation_id
            ):
                raise ValueError("Automatisation introuvable")
            result = request_json(
                f"{SUPERVISOR_API}/config/automation/config/"
                f"{urllib.parse.quote(automation_id, safe='_-')}",
                method="DELETE",
                token=supervisor_token,
                timeout=60,
            )
            request_json(
                f"{SUPERVISOR_API}/services/automation/reload",
                method="POST",
                token=supervisor_token,
                payload={},
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
    interval = max(5, min(300, int(options.get("heartbeat_seconds", 5))))
    relay_url = str(options.get("relay_url", "")).strip()
    relay_house_id = str(options.get("relay_house_id", "")).strip()
    relay_token = str(options.get("relay_token", "")).strip()
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        raise SystemExit("Accès interne à Home Assistant indisponible")
    if not enrollment_code and not (relay_url and relay_house_id and relay_token):
        raise SystemExit("Configuration incomplète : code d'installation ou liaison VPS requis")

    state = read_json(STATE_PATH, {})
    last_full_inventory_at = 0.0
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
        cycle_started_at = time.monotonic()
        try:
            if not state.get("token"):
                state = enroll(portal_url, enrollment_code)
            full_inventory = (
                last_full_inventory_at == 0.0 or
                time.monotonic() - last_full_inventory_at >= FULL_INVENTORY_SECONDS
            )
            summary = home_assistant_summary(
                supervisor_token,
                full_inventory=full_inventory,
            )
            command_results = state.pop("command_results", [])
            if command_results:
                summary["commandResults"] = command_results
            heartbeat_result = heartbeat(portal_url, str(state["token"]), summary)
            if full_inventory:
                last_full_inventory_at = time.monotonic()
            interval = max(5, min(300, int(heartbeat_result.get("nextHeartbeatSeconds", 5))))
            commands = heartbeat_result.get("commands")
            if isinstance(commands, list):
                results = []
                for command in commands[:20]:
                    if not isinstance(command, dict):
                        continue
                    result = relay_command(supervisor_token, command)
                    results.append({
                        "id": str(command.get("id", "")),
                        "ok": bool(result.get("ok")),
                        "error": str(result.get("error", ""))[:240],
                    })
                if results:
                    state["command_results"] = results
                    write_state(state)
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
        cycle_duration = time.monotonic() - cycle_started_at
        time.sleep(max(0.2, interval - cycle_duration))


if __name__ == "__main__":
    main()
