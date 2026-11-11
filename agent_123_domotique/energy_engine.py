"""Versioned, local site power balance shared by every La Box display."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import re
import threading

ENTITY_ID = 'sensor.home_energy_balance'
SCHEMA_VERSION = 1
MAX_SOURCE_AGE = 120
MAX_DELAY = 600


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def iso(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat()


def source_power(row, now):
    if not isinstance(row, dict):
        return None
    attributes = row.get('attributes', {})
    report = timestamp(row.get('last_reported') or row.get('last_updated'))
    if report is None or not -30 <= now - report <= MAX_SOURCE_AGE or attributes.get('stale') is True:
        return None
    captured = attributes.get('captured_at')
    if captured is not None and (type(captured) not in (int, float) or not math.isfinite(captured)
                                 or not -60 <= now - captured <= MAX_SOURCE_AGE):
        return None
    raw = row.get('state')
    if type(raw) not in (str, int, float) or isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = float(str(raw).replace(',', '.'))
    except (ValueError, OverflowError):
        return None
    unit = str(attributes.get('unit_of_measurement', '')).lower()
    if not math.isfinite(value) or unit not in ('w', 'kw'):
        return None
    watts = value * (1000 if unit == 'kw' else 1)
    return watts if math.isfinite(watts) else None


def micro(row, entity_id):
    match = re.fullmatch(r'sensor\.1_2_3_home_deye_([0-9]+)_power', entity_id)
    attributes = row.get('attributes', {}) if row else {}
    return bool(match and attributes.get('platform') == 'solarman'
                and str(attributes.get('serial_number')) == match[1]
                and attributes.get('original_name') == 'Power'
                and attributes.get('model') == 'M100G4 / M200G4')


class EnergyEngine:
    def __init__(self, validate_configuration):
        self.validate_configuration = validate_configuration
        self.previous = None
        self.lock = threading.Lock()

    def calculate(self, document, states, now):
        with self.lock:
            return self._calculate(document, states, now)

    def _calculate(self, document, states, now):
        configuration = document.get('configuration', {})
        config = configuration.get('energyMetering')
        payload = {'version': SCHEMA_VERSION, 'engineVersion': 1,
                   'installationId': document.get('installationId'),
                   'configuration': {'electricalSupply': configuration.get('electricalSupply'),
                                     'energyMetering': deepcopy(config)},
                   'observedAt': iso(now), 'measuredAt': None,
                   'validUntil': iso(now + 30), 'status': 'unavailable',
                   'values': {'solar': None, 'grid': None, 'home': None, 'battery': None}}
        if not config or config.get('scope') != 'site':
            self.previous = None
            payload['status'] = 'unconfigured'
            return payload
        try:
            self.validate_configuration(config, configuration.get('electricalSupply'))
        except (ValueError, TypeError, KeyError):
            self.previous = None
            return payload
        if not isinstance(states, list):
            self.previous = None
            return payload
        grouped = {}
        for row in states:
            if isinstance(row, dict):
                grouped.setdefault(row.get('entity_id'), []).append(row)
        selected = config['production'] + config['grid'] + config['battery']
        selected += [pair['ac'] for pair in config.get('hybrid', [])]
        rows = {entity_id: grouped[entity_id][0] if len(grouped.get(entity_id, [])) == 1 else None
                for entity_id in selected}
        # Preserve the same total-or-children exclusion as the installation contract.
        covered = set()
        for entity_id in selected:
            attributes = rows[entity_id].get('attributes', {}) if rows[entity_id] else {}
            ancestry = attributes.get('source_entity_ids', [])
            if not isinstance(ancestry, list):
                self.previous = None
                return payload
            lineage = [entity_id] + ancestry
            if not isinstance(lineage, list) or any(not isinstance(item, str) or item in covered for item in lineage):
                self.previous = None
                return payload
            covered.update(lineage)
        for pair in config.get('hybrid', []):
            serial = re.fullmatch(r'sensor\.1_2_3_home_deye_([0-9]+)_pv_power', pair['production'])[1]
            for entity_id, name in ((pair['production'], 'PV Power'), (pair['ac'], 'Power')):
                attributes = rows[entity_id].get('attributes', {}) if rows[entity_id] else {}
                if (attributes.get('platform') != 'solarman' or str(attributes.get('serial_number')) != serial
                        or attributes.get('model') != 'SG0*HP3' or attributes.get('original_name') != name):
                    self.previous = None
                    return payload
        powers = {entity_id: source_power(row, now) for entity_id, row in rows.items()}
        production = config['production']
        hybrid_ac = {pair['production']: pair['ac'] for pair in config.get('hybrid', [])}
        balance_sources = [hybrid_ac.get(entity_id, entity_id) for entity_id in production]
        grid_sign = -1 if config['gridDirection'] == 'export_positive' else 1
        battery_sign = -1 if config['batteryDirection'] == 'charge_positive' else 1

        def total(ids, sign=1, positive=False):
            values = [powers[entity_id] for entity_id in ids]
            if any(value is None or positive and value < 0 for value in values):
                return None
            result = sum(values) * sign
            return result if math.isfinite(result) else None

        solar = total(production, positive=True)
        grid = total(config['grid'], grid_sign)
        battery = total(config['battery'], battery_sign) if config['batteryMode'] == 'separate_ac' else 0
        balance = total(balance_sources)
        estimated = False
        sun_rows = grouped.get('sun.sun', [])
        sun = sun_rows[0] if len(sun_rows) == 1 else {}
        sun_stamp = timestamp(sun.get('last_reported') or sun.get('last_updated'))
        sun_attributes = sun.get('attributes', {})
        night = sun_stamp is not None and -30 <= now-sun_stamp <= 1500 and sun.get('state') == 'below_horizon'
        elevation = sun_attributes.get('elevation')
        dusk = (sun_stamp is not None and -30 <= now-sun_stamp <= 1500
                and sun.get('state') == 'above_horizon' and sun_attributes.get('rising') is False
                and type(elevation) in (int, float) and -6 <= elevation <= 3
                and bool(hybrid_ac) and all(powers.get(entity_id) is not None and 0 <= powers[entity_id] <= 10
                                          for entity_id in hybrid_ac))
        if sun_attributes.get('stale') is not True and (night or dusk):
            sleeping = [entity_id for entity_id in production if micro(rows[entity_id], entity_id)
                        and rows[entity_id].get('state') in ('unknown', 'unavailable')]
            if sleeping and (config['batteryMode'] == 'none' or hybrid_ac):
                for entity_id in sleeping:
                    powers[entity_id] = 0
                solar, balance = total(production, positive=True), total(balance_sources)
                estimated = True
        home = balance + grid + battery if balance is not None and grid is not None and battery is not None else None
        if home is not None and not math.isfinite(home):
            home = None
        complete = solar is not None and grid is not None and home is not None and home >= 0 and config['batteryMode'] != 'unknown'
        payload['values'] = {'solar': solar, 'grid': grid, 'home': home if complete else None,
                             'battery': battery if config['batteryMode'] == 'separate_ac' else None}
        binding = json.dumps([document.get('agentId'), document.get('installationId'), document.get('revision'), document.get('authority')], sort_keys=True)
        if complete:
            payload.update(status='estimated' if estimated else 'measured', measuredAt=iso(now))
            if not estimated:
                self.previous = (binding, now, deepcopy(payload['values']))
            return payload
        can_delay = (config['batteryMode'] == 'none' and not hybrid_ac and home is not None and home < 0
                     and solar is not None and solar >= 0
                     and all(micro(rows[entity_id], entity_id) for entity_id in production)
                     and self.previous is not None and self.previous[0] == binding
                     and 0 <= now-self.previous[1] <= MAX_DELAY)
        if can_delay:
            payload.update(status='delayed', measuredAt=iso(self.previous[1]), values=deepcopy(self.previous[2]))
        else:
            self.previous = None
        return payload
