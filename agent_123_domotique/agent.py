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
PV_PEAK_STATE_PATH = Path("/data/pv-peak-state.json")
SUPERVISOR_API = "http://supervisor/core/api"
HOME_ASSISTANT_FRONTEND = "http://homeassistant:8123"
FULL_INVENTORY_SECONDS = 60
SOLAR_FORECAST_REFRESH_SECONDS = 15 * 60
SOLAR_FORECAST_PREFIX = "sensor.1_2_3_home_solar_forecast_"
SOLAR_FORECAST_CACHE: list[dict[str, Any]] = []
SOLAR_FORECAST_FETCHED_AT = 0.0
REGISTRY_METADATA_CACHE: dict[str, dict[str, Any]] = {}
REGISTRY_METADATA_FETCHED_AT = 0.0
REGISTRY_METADATA_REFRESH_SECONDS = 15 * 60
FAST_ENTITY_PREFIXES = (
    "sensor.inverter_",
    "sensor.onduleur_",
    "sensor.shellyem3_",
    "sensor.1_2_3_home_",
    "sensor.filtration_piscine_",
    "sensor.pac_",
    "sensor.piscine_",
    "sensor.pool_",
    "sensor.tesla_",
    "sensor.model_x_",
    "sensor.lektrico_",
    "binary_sensor.tesla_",
    "binary_sensor.model_x_",
    "switch.tesla_",
    "switch.model_x_",
    "button.tesla_",
    "button.model_x_",
    "button.lektrico_",
    "climate.",
    "weather.",
    "sun.sun",
    "light.",
    "switch.",
    "lock.",
    "cover.",
    "input_boolean.demo_",
    "input_boolean.chauffe_eau_",
    "input_number.demo_",
    "input_number.chauffe_eau_",
    "input_select.demo_",
    "input_select.chauffe_eau_",
    "sensor.1p7k_",
    "number.1p7k_",
    "binary_sensor.1p7k_",
    "switch.1p7k_",
)
SAFE_ATTRIBUTE_KEYS = (
    "unit_of_measurement",
    "current_temperature",
    "temperature",
    "hvac_action",
    "hvac_modes",
    "min_temp",
    "max_temp",
    "target_temp_step",
    "cloud_coverage",
    "battery_level",
    "charging_state",
    "door_lock",
    "date",
)
DEVICE_DAILY_ENERGY_BINDINGS = (
    (
        ("sensor.filtration_piscine_energie_totale",),
        "sensor.1_2_3_home_filtration_energy_today",
        "Filtration piscine aujourd’hui",
    ),
    (
        (
            "sensor.pac_piscine_energie_totale",
            "sensor.piscine_pac_energie_totale",
            "sensor.pool_heat_pump_energy_total",
        ),
        "sensor.1_2_3_home_pool_heat_pump_energy_today",
        "PAC piscine aujourd’hui",
    ),
    (
        (
            "sensor.chauffe_eau_energie_totale",
            "sensor.ballon_eau_chaude_energie_totale",
            "sensor.ce_energie_totale",
        ),
        "sensor.1_2_3_home_water_heater_energy_today",
        "Chauffe-eau aujourd’hui",
    ),
    (
        (
            "sensor.1p7k_energy",
            "sensor.1p7k_total_energy",
            "sensor.lektrico_energy_total",
        ),
        "sensor.1_2_3_home_vehicle_charge_energy_today",
        "Recharge véhicule aujourd’hui",
    ),
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
PV_POWER_ENTITY_IDS = (
    "sensor.onduleur_pv_power",
    "sensor.inverter_pv_power",
    "sensor.deye_active_power_pv",
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


def registry_metadata_from_results(
    entity_result: Any,
    device_result: Any,
) -> dict[str, dict[str, Any]]:
    """Joint les registres HA sans exposer de secret ni d'adresse locale."""
    entities = entity_result.get("result") if isinstance(entity_result, dict) else entity_result
    devices = device_result.get("result") if isinstance(device_result, dict) else device_result
    if not isinstance(entities, list):
        entities = []
    if not isinstance(devices, list):
        devices = []
    devices_by_id = {
        str(device.get("id")): device
        for device in devices
        if isinstance(device, dict) and device.get("id")
    }
    metadata: dict[str, dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict) or not entity.get("entity_id"):
            continue
        values: dict[str, Any] = {}
        platform = entity.get("platform")
        if isinstance(platform, str) and platform:
            values["platform"] = platform[:80]
        original_name = entity.get("original_name")
        if isinstance(original_name, str) and original_name:
            values["original_name"] = original_name[:180]
        device = devices_by_id.get(str(entity.get("device_id")), {})
        if isinstance(device, dict):
            device_name = device.get("name_by_user") or device.get("name")
            if isinstance(device_name, str) and device_name:
                values["device_name"] = device_name[:180]
            for key in ("manufacturer", "model", "serial_number"):
                value = device.get(key)
                if isinstance(value, (str, int, float)) and str(value):
                    values[key] = str(value)[:180]
        if values:
            metadata[str(entity["entity_id"])] = values
    return metadata


def home_assistant_registry_metadata(supervisor_token: str) -> dict[str, dict[str, Any]]:
    global REGISTRY_METADATA_CACHE, REGISTRY_METADATA_FETCHED_AT
    if (
        REGISTRY_METADATA_CACHE
        and time.monotonic() - REGISTRY_METADATA_FETCHED_AT < REGISTRY_METADATA_REFRESH_SECONDS
    ):
        return REGISTRY_METADATA_CACHE
    try:
        entities = home_assistant_ws_command(
            supervisor_token,
            {"type": "config/entity_registry/list"},
            timeout=12,
        )
        devices = home_assistant_ws_command(
            supervisor_token,
            {"type": "config/device_registry/list"},
            timeout=12,
        )
        REGISTRY_METADATA_CACHE = registry_metadata_from_results(entities, devices)
        REGISTRY_METADATA_FETCHED_AT = time.monotonic()
    except Exception as error:
        log(f"Métadonnées du registre Home Assistant indisponibles ({error})")
    return REGISTRY_METADATA_CACHE


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
        "User-Agent": "Agent-123-Domotique/0.5.27",
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
    if not math.isfinite(current) or current < 0:
        return None
    if not isinstance(history, list):
        return None
    series = history[0] if history and isinstance(history[0], list) else history
    values: list[float] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get("state"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0:
            values.append(value)
    if not values:
        return None
    if not math.isclose(values[-1], current, rel_tol=0, abs_tol=1e-9):
        values.append(current)
    total = 0.0
    previous = values[0]
    for value in values[1:]:
        difference = value - previous
        if difference >= 0:
            total += difference
            previous = value
            continue
        jitter_tolerance = max(0.1, previous * 0.001)
        if abs(difference) <= jitter_tolerance:
            continue
        total += value
        previous = value
    return round(total, 4)


def daily_pv_peak(
    states: list[Any],
    previous: dict[str, Any],
    *,
    timezone_name: str = "Europe/Paris",
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_timezone = timezone.utc
    current_time = now.astimezone(local_timezone) if now else datetime.now(local_timezone)
    current_date = current_time.date().isoformat()
    by_entity_id = {
        str(item.get("entity_id")): item
        for item in states
        if isinstance(item, dict) and item.get("entity_id")
    }
    source = next(
        (by_entity_id[entity_id] for entity_id in PV_POWER_ENTITY_IDS if entity_id in by_entity_id),
        None,
    )
    try:
        current_power = max(0.0, float(source.get("state", "0"))) if source else 0.0
    except (TypeError, ValueError):
        current_power = 0.0
    attributes = source.get("attributes") if isinstance(source, dict) else {}
    if not isinstance(attributes, dict):
        attributes = {}
    if str(attributes.get("unit_of_measurement", "W")).lower() == "kw":
        current_power *= 1000

    previous_peak = 0.0
    if str(previous.get("date", "")) == current_date:
        try:
            previous_peak = max(0.0, float(previous.get("peak_w", 0)))
        except (TypeError, ValueError):
            previous_peak = 0.0
    return {
        "date": current_date,
        "peak_w": round(max(previous_peak, current_power), 1),
    }


def maintain_daily_pv_peak(
    supervisor_token: str,
    config: dict[str, Any],
    states: list[Any],
) -> None:
    previous = read_json(PV_PEAK_STATE_PATH, {})
    peak = daily_pv_peak(
        states,
        previous,
        timezone_name=str(config.get("time_zone", "Europe/Paris")),
    )
    if peak != previous:
        write_state_to = PV_PEAK_STATE_PATH
        temporary = write_state_to.with_suffix(".tmp")
        temporary.write_text(json.dumps(peak), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(write_state_to)

    entity_state = {
        "entity_id": "sensor.pic_pv_jour",
        "state": str(peak["peak_w"]),
        "attributes": {
            "friendly_name": "Pic PV jour",
            "device_class": "power",
            "state_class": "measurement",
            "unit_of_measurement": "W",
            "icon": "mdi:solar-power",
            "date": peak["date"],
            "managed_by": "Agent 1.2.3 Domotique",
        },
    }
    request_json(
        f"{SUPERVISOR_API}/states/sensor.pic_pv_jour",
        method="POST",
        token=supervisor_token,
        payload={
            "state": entity_state["state"],
            "attributes": entity_state["attributes"],
        },
    )

    for index, item in enumerate(states):
        if isinstance(item, dict) and item.get("entity_id") == "sensor.pic_pv_jour":
            states[index] = entity_state
            break
    else:
        states.append(entity_state)


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


def device_daily_energy_inventory(
    supervisor_token: str,
    config: dict[str, Any],
    states: list[Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Calcule les consommations journalières des équipements suivis."""
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
        entries: list[dict[str, Any]] = []
        for candidates, target_entity_id, name in DEVICE_DAILY_ENERGY_BINDINGS:
            source_entity_id = next(
                (entity_id for entity_id in candidates if entity_id in by_entity_id),
                "",
            )
            if not source_entity_id:
                continue
            current = by_entity_id[source_entity_id]
            encoded_entity_id = urllib.parse.quote(source_entity_id, safe="._")
            history = request_json(
                f"{SUPERVISOR_API}/history/period/{encoded_start}"
                f"?filter_entity_id={encoded_entity_id}&minimal_response&no_attributes",
                token=supervisor_token,
            )
            delta = daily_energy_delta(str(current.get("state", "")), history)
            if delta is None:
                continue
            attributes = current.get("attributes") if isinstance(current, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}
            entries.append({
                "entityId": target_entity_id,
                "name": name,
                "domain": "sensor",
                "state": str(delta),
                "deviceClass": "energy",
                "attributes": {
                    "unit_of_measurement": attributes.get("unit_of_measurement", "kWh"),
                    "source_entity_id": source_entity_id,
                },
            })
        return entries
    except Exception as error:
        log(f"Consommations journalières des équipements indisponibles ({error})")
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
    """Publie un référentiel énergétique commun au portail et à l'app."""
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
    maintain_daily_pv_peak(supervisor_token, config, states)
    available = sum(
        1 for state in states
        if isinstance(state, dict) and state.get("state") not in {"unavailable", "unknown"}
    )
    registry_metadata = home_assistant_registry_metadata(supervisor_token) if full_inventory else {}
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
        safe_attributes = {
            key: attributes[key]
            for key in SAFE_ATTRIBUTE_KEYS
            if key in attributes
        }
        safe_attributes.update(registry_metadata.get(entity_id, {}))
        inventory.append({
            "entityId": entity_id,
            "name": str(attributes.get("friendly_name", entity_id)),
            "domain": entity_id.split(".", 1)[0] if "." in entity_id else "",
            "state": str(state.get("state", "")),
            "deviceClass": attributes.get("device_class"),
            "attributes": safe_attributes,
        })
    if full_inventory:
        inventory.extend(shelly_daily_energy_inventory(
            supervisor_token,
            config,
            states,
        ))
        inventory.extend(device_daily_energy_inventory(
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
    return _refresh_solar_forecast_inventory(supervisor_token, states, now)


def lektrico_off_peak_automation(payload: dict[str, Any]) -> dict[str, Any]:
    charger_state_entity_id = str(payload.get("chargerStateEntityId", "")).strip()
    dynamic_limit_entity_id = str(payload.get("dynamicLimitEntityId", "")).strip()
    start_button_entity_id = str(payload.get("startButtonEntityId", "")).strip()
    stop_button_entity_id = str(payload.get("stopButtonEntityId", "")).strip()
    entity_ids = (
        charger_state_entity_id,
        dynamic_limit_entity_id,
        start_button_entity_id,
        stop_button_entity_id,
    )
    if any(
        len(entity_id.split(".", 1)) != 2
        or not all(part.replace("_", "").isalnum() for part in entity_id.split(".", 1))
        for entity_id in entity_ids
    ):
        raise ValueError("Entités Lektrico invalides")
    if not dynamic_limit_entity_id.startswith("number."):
        raise ValueError("Limite dynamique Lektrico invalide")
    if not start_button_entity_id.startswith("button.") or not stop_button_entity_id.startswith(
        "button."
    ):
        raise ValueError("Commandes Lektrico invalides")

    periods = payload.get("offPeakPeriods")
    if not isinstance(periods, list) or not periods:
        periods = [{"start": "22:00", "end": "06:00"}]
    normalized_periods: list[tuple[str, str, int, int]] = []
    for period in periods[:4]:
        if not isinstance(period, dict):
            continue
        start = str(period.get("start", "")).strip()
        end = str(period.get("end", "")).strip()
        try:
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")
        except ValueError:
            continue
        normalized_periods.append((
            start,
            end,
            start_time.hour * 60 + start_time.minute,
            end_time.hour * 60 + end_time.minute,
        ))
    if not normalized_periods:
        normalized_periods = [("22:00", "06:00", 1320, 360)]
    maximum_amps = max(6, min(64, round(float(payload.get("maximumAmps", 16)))))

    time_expressions = []
    for _, _, start_minutes, end_minutes in normalized_periods:
        if start_minutes == end_minutes:
            time_expressions.append("true")
        elif start_minutes < end_minutes:
            time_expressions.append(
                f"({start_minutes} <= minutes and minutes < {end_minutes})"
            )
        else:
            time_expressions.append(
                f"(minutes >= {start_minutes} or minutes < {end_minutes})"
            )
    off_peak_template = (
        "{% set minutes = now().hour * 60 + now().minute %} "
        "{{ " + " or ".join(time_expressions) + " }}"
    )
    plugged_template = (
        "{{ states('" + charger_state_entity_id + "') | lower in "
        "['starting', 'finishing', 'stopped', 'complete', 'no_power', "
        "'need_auth', 'locked', 'suspended_ev', 'suspended_evse', "
        "'charging', 'connected', 'paused', 'paused_by_scheduler'] }}"
    )
    triggers: list[dict[str, Any]] = [
        {"platform": "homeassistant", "event": "start"},
        {"platform": "state", "entity_id": charger_state_entity_id},
    ]
    for index, (start, end, _, _) in enumerate(normalized_periods):
        triggers.extend((
            {"platform": "time", "at": f"{start}:00", "id": f"start_{index}"},
            {"platform": "time", "at": f"{end}:00", "id": f"end_{index}"},
        ))
    return {
        "id": "ma_maison_lektrico_off_peak_charging",
        "alias": "1.2.3 Home · Recharge heures creuses Lektrico",
        "description": (
            "Recharge uniquement pendant les heures creuses configurées dans le portail, "
            "véhicule branché."
        ),
        "trigger": triggers,
        "condition": [],
        "action": [{
            "choose": [{
                "conditions": [
                    {"condition": "template", "value_template": off_peak_template},
                    {"condition": "template", "value_template": plugged_template},
                ],
                "sequence": [
                    {
                        "service": "number.set_value",
                        "target": {"entity_id": dynamic_limit_entity_id},
                        "data": {"value": maximum_amps},
                    },
                    {
                        "service": "button.press",
                        "target": {"entity_id": start_button_entity_id},
                    },
                ],
            }],
            "default": [
                {"condition": "template", "value_template": plugged_template},
                {
                    "service": "button.press",
                    "target": {"entity_id": stop_button_entity_id},
                },
            ],
        }],
        "mode": "restart",
    }
def _refresh_solar_forecast_inventory(
    supervisor_token: str,
    states: list[dict[str, Any]],
    now: float,
) -> list[dict[str, Any]]:
    global SOLAR_FORECAST_CACHE, SOLAR_FORECAST_FETCHED_AT
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
        elif action == "ha.water_heater.solar_plan":
            automation_id = str(payload.get("automationId", "")).strip()
            name = str(payload.get("name", "ECS solaire intelligent")).strip()
            switch_entity_id = str(payload.get("switchEntityId", "")).strip()
            grid_power_entity_id = str(payload.get("gridPowerEntityId", "")).strip()
            fallback_start = str(payload.get("fallbackStart", "12:00")).strip()
            fallback_end = str(payload.get("fallbackEnd", "16:00")).strip()
            surplus_threshold = int(payload.get("surplusThresholdW", 2700))
            import_threshold = int(payload.get("importThresholdW", 300))

            if not automation_id or not all(
                char.isalnum() or char in {"_", "-"}
                for char in automation_id
            ):
                raise ValueError("Identifiant d’automatisation invalide")
            if len(name) < 3 or len(name) > 80:
                raise ValueError("Nom d’automatisation invalide")
            for value in (fallback_start, fallback_end):
                try:
                    datetime.strptime(value, "%H:%M")
                except ValueError as error:
                    raise ValueError("Horaire de secours invalide") from error
            if not 500 <= surplus_threshold <= 12000:
                raise ValueError("Seuil de surplus invalide")
            if not 0 <= import_threshold <= 3000:
                raise ValueError("Seuil d’import invalide")

            switch_parts = switch_entity_id.split(".", 1)
            grid_parts = grid_power_entity_id.split(".", 1)
            if (
                len(switch_parts) != 2
                or switch_parts[0] != "switch"
                or len(grid_parts) != 2
                or grid_parts[0] != "sensor"
                or not all(
                    part.replace("_", "").isalnum()
                    for part in (*switch_parts, *grid_parts)
                )
            ):
                raise ValueError("Capteur ou commande ECS invalide")

            states = request_json(
                f"{SUPERVISOR_API}/states",
                token=supervisor_token,
            )
            available_entity_ids = {
                str(state.get("entity_id", ""))
                for state in states
                if isinstance(state, dict)
            }
            if switch_entity_id not in available_entity_ids:
                raise ValueError("Commande du ballon introuvable")
            if grid_power_entity_id not in available_entity_ids:
                raise ValueError("Capteur de puissance réseau introuvable")

            fallback_start_at = f"{fallback_start}:00"
            fallback_end_at = f"{fallback_end}:00"
            result = request_json(
                f"{SUPERVISOR_API}/config/automation/config/{automation_id}",
                method="POST",
                token=supervisor_token,
                payload={
                    "id": automation_id,
                    "alias": name,
                    "description": (
                        "Priorité au surplus solaire. Secours de "
                        f"{fallback_start} à {fallback_end} pour garantir l’eau chaude. "
                        "Le thermostat interne du ballon reste prioritaire."
                    ),
                    "trigger": [
                        {
                            "platform": "numeric_state",
                            "entity_id": [grid_power_entity_id],
                            "below": -surplus_threshold,
                            "for": {"hours": 0, "minutes": 5, "seconds": 0},
                            "id": "solaire_disponible",
                        },
                        {
                            "platform": "numeric_state",
                            "entity_id": [grid_power_entity_id],
                            "above": import_threshold,
                            "for": {"hours": 0, "minutes": 3, "seconds": 0},
                            "id": "reseau_sollicite",
                        },
                        {
                            "platform": "time",
                            "at": fallback_start_at,
                            "id": "secours_jour",
                        },
                        {
                            "platform": "time",
                            "at": fallback_end_at,
                            "id": "arret",
                        },
                    ],
                    "condition": [],
                    "action": [{
                        "choose": [
                            {
                                "conditions": [{
                                    "condition": "trigger",
                                    "id": ["solaire_disponible"],
                                }],
                                "sequence": [{
                                    "service": "switch.turn_on",
                                    "target": {"entity_id": switch_entity_id},
                                }],
                            },
                            {
                                "conditions": [
                                    {
                                        "condition": "trigger",
                                        "id": ["reseau_sollicite"],
                                    },
                                    {
                                        "condition": "or",
                                        "conditions": [
                                            {
                                                "condition": "time",
                                                "before": fallback_start_at,
                                            },
                                            {
                                                "condition": "time",
                                                "after": fallback_end_at,
                                            },
                                        ],
                                    },
                                ],
                                "sequence": [{
                                    "service": "switch.turn_off",
                                    "target": {"entity_id": switch_entity_id},
                                }],
                            },
                            {
                                "conditions": [{
                                    "condition": "trigger",
                                    "id": ["secours_jour"],
                                }],
                                "sequence": [{
                                    "service": "switch.turn_on",
                                    "target": {"entity_id": switch_entity_id},
                                }],
                            },
                            {
                                "conditions": [{
                                    "condition": "trigger",
                                    "id": ["arret"],
                                }],
                                "sequence": [{
                                    "service": "switch.turn_off",
                                    "target": {"entity_id": switch_entity_id},
                                }],
                            },
                        ],
                    }],
                    "mode": "restart",
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
        elif action == "ha.ev_charger.off_peak_plan":
            automation = lektrico_off_peak_automation(payload)
            result = request_json(
                f"{SUPERVISOR_API}/config/automation/config/"
                "ma_maison_lektrico_off_peak_charging",
                method="POST",
                token=supervisor_token,
                payload=automation,
                timeout=60,
            )
            request_json(
                f"{SUPERVISOR_API}/services/automation/reload",
                method="POST",
                token=supervisor_token,
                payload={},
                timeout=60,
            )
        elif action == "ha.ev_charger.solar_plan":
            automation_id = str(payload.get(
                "automationId",
                "ma_maison_lektrico_solar_charging",
            )).strip()
            grid_power_entity_id = str(payload.get("gridPowerEntityId", "")).strip()
            battery_power_entity_id = str(payload.get("batteryPowerEntityId", "")).strip()
            battery_level_entity_id = str(payload.get("batteryLevelEntityId", "")).strip()
            charger_state_entity_id = str(payload.get("chargerStateEntityId", "")).strip()
            charger_current_entity_id = str(payload.get("chargerCurrentEntityId", "")).strip()
            charger_voltage_entity_id = str(payload.get("chargerVoltageEntityId", "")).strip()
            dynamic_limit_entity_id = str(payload.get("dynamicLimitEntityId", "")).strip()
            start_button_entity_id = str(payload.get("startButtonEntityId", "")).strip()
            stop_button_entity_id = str(payload.get("stopButtonEntityId", "")).strip()
            fault_entity_ids = payload.get("faultEntityIds", [])
            reserve_watts = int(payload.get("reserveWatts", 100))
            minimum_battery_percent = int(payload.get("minimumBatteryPercent", 95))
            minimum_amps = int(payload.get("minimumAmps", 6))
            maximum_amps = int(payload.get("maximumAmps", 32))

            if not automation_id or not all(
                char.isalnum() or char in {"_", "-"}
                for char in automation_id
            ):
                raise ValueError("Identifiant d’automatisation invalide")
            if not 0 <= reserve_watts <= 1000:
                raise ValueError("Marge réseau invalide")
            if not 0 <= minimum_battery_percent <= 100:
                raise ValueError("Seuil de batterie invalide")
            if not 6 <= minimum_amps <= maximum_amps <= 80:
                raise ValueError("Limites de courant invalides")
            if not isinstance(fault_entity_ids, list):
                raise ValueError("Liste des défauts invalide")

            required_entities = {
                grid_power_entity_id: "sensor",
                charger_state_entity_id: "sensor",
                charger_current_entity_id: "sensor",
                charger_voltage_entity_id: "sensor",
                dynamic_limit_entity_id: "number",
                start_button_entity_id: "button",
                stop_button_entity_id: "button",
            }
            if battery_power_entity_id:
                required_entities[battery_power_entity_id] = "sensor"
            if battery_level_entity_id:
                required_entities[battery_level_entity_id] = "sensor"
            for entity_id, expected_domain in required_entities.items():
                parts = entity_id.split(".", 1)
                if (
                    len(parts) != 2
                    or parts[0] != expected_domain
                    or not all(part.replace("_", "").isalnum() for part in parts)
                ):
                    raise ValueError("Capteur ou commande Lektrico invalide")
            for entity_id in fault_entity_ids:
                parts = str(entity_id).split(".", 1)
                if (
                    len(parts) != 2
                    or parts[0] != "binary_sensor"
                    or not all(part.replace("_", "").isalnum() for part in parts)
                ):
                    raise ValueError("Capteur de défaut Lektrico invalide")

            states = request_json(
                f"{SUPERVISOR_API}/states",
                token=supervisor_token,
            )
            available_entity_ids = {
                str(state.get("entity_id", ""))
                for state in states
                if isinstance(state, dict)
            }
            missing_entities = [
                entity_id
                for entity_id in (*required_entities.keys(), *fault_entity_ids)
                if entity_id not in available_entity_ids
            ]
            if missing_entities:
                raise ValueError(
                    "Entité Lektrico introuvable : " + ", ".join(missing_entities)
                )

            fault_condition = " or ".join(
                f"is_state('{entity_id}', 'on')"
                for entity_id in fault_entity_ids
            ) or "false"
            battery_discharge_template = (
                "[states('" + battery_power_entity_id + "') | float(0), 0] | max"
                if battery_power_entity_id else "0"
            )
            battery_ready_template = (
                "(states('" + battery_level_entity_id + "') | float(0) >= "
                + str(minimum_battery_percent) + ")"
                if battery_level_entity_id else "true"
            )
            start_threshold_template = (
                "{{ " + battery_ready_template + " and "
                "(0 - (states('" + grid_power_entity_id + "') | float(0)) - ("
                + battery_discharge_template + ")) >= ((" + str(minimum_amps) + " * "
                "([states('" + charger_voltage_entity_id + "') | float(230), 210] | max))"
                " + " + str(reserve_watts) + ") }}"
            )
            available_template = (
                "{{ states('" + charger_state_entity_id + "') "
                "in ['connected', 'paused', 'paused_by_scheduler', 'need_auth'] and not ("
                + fault_condition + ") }}"
            )
            target_current_template = (
                "{% set grid = states('" + grid_power_entity_id + "') | float(0) %} "
                "{% set current = states('" + charger_current_entity_id + "') | float(0) %} "
                "{% set requested = states('" + dynamic_limit_entity_id + "') | float("
                + str(minimum_amps) + ") %} "
                "{% set effective_current = [current, requested] | max "
                "if is_state('" + charger_state_entity_id + "', 'charging') else current %} "
                "{% set voltage = [states('" + charger_voltage_entity_id + "') | float(230), 210] | max %} "
                "{% set battery_discharge = " + battery_discharge_template + " %} "
                "{% set desired = (effective_current + ((-grid - battery_discharge - "
                + str(reserve_watts) + ") / voltage)) "
                "| round(0, 'floor') | int %} "
                "{{ [[desired, " + str(minimum_amps) + "] | max, "
                + str(maximum_amps) + "] | min }}"
            )
            insufficient_surplus_template = (
                "{{ is_state('" + charger_state_entity_id + "', 'charging') and "
                "(as_timestamp(now()) - as_timestamp(states['"
                + charger_state_entity_id + "'].last_changed)) >= 20 and "
                "(not " + battery_ready_template + " or "
                "([states('" + charger_current_entity_id + "') | float(0), "
                "states('" + dynamic_limit_entity_id + "') | float("
                + str(minimum_amps) + ")] | max + "
                "((0 - (states('" + grid_power_entity_id + "') | float(0)) - ("
                + battery_discharge_template + ") - "
                + str(reserve_watts) + ") / "
                "([states('" + charger_voltage_entity_id + "') | float(230), 210] | max))) < "
                + str(minimum_amps) + ") }}"
            )
            sufficient_surplus_template = (
                "{{ is_state('" + charger_state_entity_id + "', 'charging') and "
                "([states('" + charger_current_entity_id + "') | float(0), "
                "states('" + dynamic_limit_entity_id + "') | float("
                + str(minimum_amps) + ")] | max + "
                "((0 - (states('" + grid_power_entity_id + "') | float(0)) - ("
                + battery_discharge_template + ") - "
                + str(reserve_watts) + ") / "
                "([states('" + charger_voltage_entity_id + "') | float(230), 210] | max))) >= "
                + str(minimum_amps) + " }}"
            )

            automation_payload = {
                "id": automation_id,
                "alias": "1.2.3 Home · Recharge solaire Lektrico",
                "description": (
                    "Ajuste la limite dynamique de la borne Lektrico sur le surplus "
                    f"solaire sans décharger la batterie, après {minimum_battery_percent} % "
                    f"de charge et avec une marge réseau de {reserve_watts} W."
                ),
                "trigger": [
                    {
                        "platform": "time_pattern",
                        "seconds": "/5",
                        "id": "ajustement",
                    },
                    {
                        "platform": "template",
                        "value_template": start_threshold_template,
                        "for": {"hours": 0, "minutes": 0, "seconds": 30},
                        "id": "demarrage",
                    },
                    {
                        "platform": "template",
                        "value_template": insufficient_surplus_template,
                        "for": {"hours": 0, "minutes": 0, "seconds": 45},
                        "id": "arret_surplus",
                    },
                    {
                        "platform": "numeric_state",
                        "entity_id": [grid_power_entity_id],
                        "above": 700,
                        "for": {"hours": 0, "minutes": 1, "seconds": 0},
                        "id": "arret_import",
                    },
                    *([{
                        "platform": "state",
                        "entity_id": fault_entity_ids,
                        "to": "on",
                        "id": "arret_defaut",
                    }] if fault_entity_ids else []),
                    {
                        "platform": "state",
                        "entity_id": [charger_state_entity_id],
                        "to": "error",
                        "id": "arret_defaut",
                    },
                ],
                "condition": [],
                "action": [{
                    "choose": [
                        {
                            "conditions": [{
                                "condition": "trigger",
                                "id": ["arret_surplus", "arret_import", "arret_defaut"],
                            }],
                            "sequence": [
                                {
                                    "service": "button.press",
                                    "target": {"entity_id": stop_button_entity_id},
                                },
                            ],
                        },
                        {
                            "conditions": [
                                {
                                    "condition": "trigger",
                                    "id": ["demarrage"],
                                },
                                {
                                    "condition": "template",
                                    "value_template": available_template,
                                },
                            ],
                            "sequence": [
                                {
                                    "service": "number.set_value",
                                    "target": {"entity_id": dynamic_limit_entity_id},
                                    "data": {"value": minimum_amps},
                                },
                                {
                                    "service": "button.press",
                                    "target": {"entity_id": start_button_entity_id},
                                },
                            ],
                        },
                        {
                            "conditions": [
                                {
                                    "condition": "trigger",
                                    "id": ["ajustement"],
                                },
                                {
                                    "condition": "state",
                                    "entity_id": charger_state_entity_id,
                                    "state": "charging",
                                },
                                {
                                    "condition": "template",
                                    "value_template": "{{ not (" + fault_condition + ") }}",
                                },
                                {
                                    "condition": "template",
                                    "value_template": sufficient_surplus_template,
                                },
                            ],
                            "sequence": [{
                                "service": "number.set_value",
                                "target": {"entity_id": dynamic_limit_entity_id},
                                "data": {"value": target_current_template},
                            }],
                        },
                        {
                            "conditions": [
                                {
                                    "condition": "trigger",
                                    "id": ["ajustement"],
                                },
                                {
                                    "condition": "template",
                                    "value_template": start_threshold_template,
                                },
                                {
                                    "condition": "template",
                                    "value_template": available_template,
                                },
                                {
                                    "condition": "template",
                                    "value_template": "{{ (now().second | int) % 15 == 0 }}",
                                },
                            ],
                            "sequence": [
                                {
                                    "service": "number.set_value",
                                    "target": {"entity_id": dynamic_limit_entity_id},
                                    "data": {"value": target_current_template},
                                },
                                {
                                    "service": "button.press",
                                    "target": {"entity_id": start_button_entity_id},
                                },
                            ],
                        },
                    ],
                }],
                "mode": "restart",
                "max_exceeded": "silent",
            }
            result = request_json(
                f"{SUPERVISOR_API}/config/automation/config/"
                f"{urllib.parse.quote(automation_id, safe='_-')}",
                method="POST",
                token=supervisor_token,
                payload=automation_payload,
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
            raw_start = str(payload.get("start", "")).strip()
            raw_end = str(payload.get("end", "")).strip()
            raw_entity_id = str(payload.get("entityId", "")).strip()
            if not raw_start or not raw_entity_id:
                raise ValueError("Période ou entité manquante")
            try:
                start_time = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                end_time = (
                    datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
                    if raw_end else None
                )
            except ValueError as error:
                raise ValueError("Période d'historique invalide") from error
            if end_time is not None:
                if end_time <= start_time:
                    raise ValueError("La fin de l'historique doit suivre le début")
                if end_time - start_time > timedelta(days=2):
                    raise ValueError("Période d'historique trop longue")
            start = urllib.parse.quote(raw_start, safe=":TZ+-")
            entity_id = urllib.parse.quote(raw_entity_id, safe="._")
            query = f"filter_entity_id={entity_id}&minimal_response&no_attributes"
            if raw_end:
                end = urllib.parse.quote(raw_end, safe=":TZ+-")
                query += f"&end_time={end}"
            result = request_json(
                f"{SUPERVISOR_API}/history/period/{start}?{query}",
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
