"""Read current HA State timestamps instead of its cached REST serialization."""
import json
import re
from datetime import datetime


def live_energy_states(states, call):
    if not isinstance(states, list):
        return states
    ids = sorted({row['entity_id'] for row in states if isinstance(row, dict)
                  and isinstance(row.get('entity_id'), str)
                  and re.fullmatch(r'sensor\.[a-z0-9_]+', row['entity_id'])
                  and isinstance(row.get('attributes'), dict)
                  and row['attributes'].get('device_class') in {'power', 'energy', 'battery'}
                  and row['attributes'].get('unit_of_measurement') in {'W', 'kW', 'Wh', 'kWh', '%'}})[:256]
    if not ids:
        return states
    template = ("{% set ns=namespace(rows=[]) %}{% for id in " + json.dumps(ids) + " %}"
                "{% set s=states[id] %}{% if s is defined and s is not none %}"
                "{% set ns.rows=ns.rows+[dict(entity_id=id,state=s.state,attributes=dict(s.attributes),"
                "last_reported=s.last_reported.isoformat(),last_updated=s.last_updated.isoformat())] %}"
                "{% endif %}{% endfor %}{{ ns.rows | to_json }}")
    try:
        live = call(template)
        if isinstance(live, str):
            live = json.loads(live)
        if not isinstance(live, list):
            return states
        found = {}
        for row in live:
            if not isinstance(row, dict) or row.get('entity_id') not in ids or row['entity_id'] in found:
                return states
            stamp = datetime.fromisoformat(str(row.get('last_reported', '')).replace('Z', '+00:00'))
            if stamp.tzinfo is None or not isinstance(row.get('attributes'), dict) or not isinstance(row.get('state'), str):
                return states
            found[row['entity_id']] = row
        return [{**row, **found.get(row.get('entity_id'), {})} if isinstance(row, dict) else row for row in states]
    except (ValueError, TypeError, RuntimeError, OSError):
        # Preserve source dates on failure. Never use the heartbeat time as evidence.
        return states
