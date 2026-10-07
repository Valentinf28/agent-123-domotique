"""Read-only evidence from one connector; never certifies physical wiring.

last_reported proves a recent HA report, not a fresh inverter Modbus response.
Missing report timestamps fail closed rather than treating old cached values as live.
"""
from datetime import datetime, timezone
import math
import re

POWER_NAMES = {'production': 'PV Power', 'grid': 'Grid Power',
               'consumption': 'Load Power', 'battery': 'Battery Power'}


def inspect_measurements(entry_id, expected_serial, entries, registry, states, *, now=None):
    if not isinstance(entry_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', entry_id):
        raise ValueError('Connexion solaire invalide.')
    if not isinstance(expected_serial, str) or not re.fullmatch(r'[A-Za-z0-9-]{4,40}', expected_serial):
        raise ValueError('Renseignez le numéro de série inscrit sur l’onduleur.')
    if not all(isinstance(rows, list) for rows in (entries, registry, states)):
        raise RuntimeError('Les mesures solaires ne peuvent pas être vérifiées pour le moment.')
    now = now or datetime.now(timezone.utc)
    selected = [row for row in entries if row.get('entry_id') == entry_id and row.get('domain') == 'solarman']
    if len(selected) != 1 or selected[0].get('state') != 'loaded' or selected[0].get('disabled_by'):
        raise RuntimeError('La connexion solaire n’est pas active.')
    entities = [row for row in registry if row.get('config_entry_id') == entry_id
                and row.get('platform') == 'solarman' and not row.get('disabled_by')]
    def entity_state(name):
        matches = [row for row in entities if row.get('original_name') == name]
        if len(matches) != 1:
            return None
        readings = [row for row in states if row.get('entity_id') == matches[0].get('entity_id')]
        return readings[0] if len(readings) == 1 else None
    identity = entity_state('Device Serial Number')
    observed = str(identity.get('state', '')).strip() if identity else ''
    if identity is None:
        # The bundled SG01HP3 profile exposes its serial as a Device attribute.
        # Resolve through the same entry registry, never another inverter.
        device = entity_state('Device')
        if device and device.get('state') not in ('unknown', 'unavailable'):
            observed = str(device.get('attributes', {}).get('Serial Number', '')).strip()
    identity_status = ('missing' if observed.lower() in ('', 'unknown', 'unavailable', 'none')
                       else 'matched' if observed == expected_serial else 'mismatch')
    measurements = {}
    for key, name in POWER_NAMES.items():
        row = entity_state(name)
        result = {'status': 'missing'}
        if row:
            try:
                value = float(row.get('state'))
                unit = row.get('attributes', {}).get('unit_of_measurement')
                if not math.isfinite(value) or unit not in ('W', 'kW'):
                    raise ValueError()
                reported = datetime.fromisoformat(row.get('last_reported', '').replace('Z', '+00:00'))
                if reported.tzinfo is None:
                    raise ValueError()
                age = (now - reported).total_seconds()
                result = {'status': 'recent' if -5 <= age <= 180 else 'stale',
                          'watts': value * (1000 if unit == 'kW' else 1),
                          'reportedAt': reported.isoformat()}
            except (TypeError, ValueError, OverflowError):
                result = {'status': 'unavailable'}
        measurements[key] = result
    # Battery percentage is optional (some installations have no storage).
    # Resolve only within this connector, including when sensors were renamed.
    level = entity_state('Battery')
    battery_level = {'status': 'missing'}
    if level:
        try:
            percent = float(level.get('state'))
            attrs = level.get('attributes', {})
            if (not math.isfinite(percent) or not 0 <= percent <= 100
                    or attrs.get('unit_of_measurement') != '%'
                    or attrs.get('device_class') != 'battery'):
                raise ValueError()
            reported = datetime.fromisoformat(level.get('last_reported', '').replace('Z', '+00:00'))
            if reported.tzinfo is None:
                raise ValueError()
            age = (now - reported).total_seconds()
            battery_level = {'status': 'recent' if -5 <= age <= 180 else 'stale',
                             'percent': percent, 'reportedAt': reported.isoformat()}
        except (TypeError, ValueError, OverflowError):
            battery_level = {'status': 'unavailable'}
    return {'connector': 'solarman', 'entryId': entry_id,
            'identityStatus': identity_status,
            'readingsAvailable': identity_status == 'matched' and all(
                item['status'] == 'recent' for item in measurements.values()),
            'measurements': measurements, 'batteryLevel': battery_level,
            'physicalTestVerified': False}
