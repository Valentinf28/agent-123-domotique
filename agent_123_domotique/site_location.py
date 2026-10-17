"""Apply only confirmed geographic settings and verify the resulting core config."""
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def settings(payload):
    if not isinstance(payload, dict):
        raise ValueError('Position du site invalide.')
    result = {}
    for name, limit in [('latitude', 90), ('longitude', 180)]:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
            raise ValueError('Position du site invalide.')
        result[name] = value
    zone = payload.get('timeZone')
    if not isinstance(zone, str) or not zone or len(zone) > 100:
        raise ValueError('Fuseau horaire invalide.')
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Fuseau horaire invalide.') from None
    result['time_zone'] = zone
    return result


def matches(config, wanted):
    if not isinstance(config, dict):
        return False
    for key in ('latitude', 'longitude'):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value - wanted[key]) > 0.000001:
            return False
    return config.get('time_zone') == wanted['time_zone']


def configure(payload, call):
    wanted = settings(payload)
    before = call({'type': 'get_config'})
    changed = not matches(before, wanted)
    if changed:
        # Do not forward arbitrary fields: URLs, units, name and other settings stay intact.
        call({'type': 'config/core/update', **wanted})
    after = call({'type': 'get_config'})
    if not matches(after, wanted):
        raise RuntimeError('La box n’a pas confirmé la position du site. Vérifiez puis réessayez.')
    return {'status': 'configured', 'changed': changed,
            'position': {'latitude': after['latitude'], 'longitude': after['longitude'], 'timeZone': after['time_zone']},
            'weatherVerified': False}
