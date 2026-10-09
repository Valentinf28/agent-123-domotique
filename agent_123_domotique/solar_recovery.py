"""Recover managed SolarMAN addresses by identity, never by an open port alone."""
import json
import re
import time
from pathlib import Path
from network_discovery import discover_solarman, local_interfaces, current_adapters
from ipaddress import IPv4Address
from solar_identity import identify


def replacement(options, devices, adapters):
    serial = options.get('logger_serial')
    if type(serial) is not int:
        return None
    matches = [d for d in devices if d.get('loggerSerial') == serial]
    # Duplicate identities (even different MACs) need an installer, not a guess.
    if len(matches) != 1:
        return None
    d = matches[0]
    if d.get('status') != 'found' or d.get('connector') != 'solarman':
        return None
    if not d.get('identityVerified') and not re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}', d.get('mac', '')):
        return None
    try:
        ip = IPv4Address(d['host'])
    except (ValueError, KeyError):
        return None
    if not any(ip in i.network and ip not in (i.ip, i.network.network_address, i.network.broadcast_address)
               for i in local_interfaces(adapters)):
        return None
    return str(ip) if str(ip) != options.get('host') else None


def recover(call, ws, *, config=Path('/homeassistant_config'), discover=discover_solarman):
    """One bounded pass. Called every five minutes outside the heartbeat thread."""
    if not (config / 'custom_components/solarman/123home-bundle.json').is_file():
        return []
    entries = json.loads((config / '.storage/core.config_entries').read_text())['data']['entries']
    registry = ws({'type': 'config/entity_registry/list'}).get('result', [])
    states = {s['entity_id']: s for s in call('/states')}
    candidates = []
    now = time.time()
    for entry in entries:
        options = entry.get('options', {})
        if entry.get('domain') != 'solarman' or entry.get('disabled_by') or not options.get('logger_serial'):
            continue
        if options.get('lookup_file') != 'custom/deye_sg01hp3_readonly.yaml':
            continue
        sensors = [states[r['entity_id']] for r in registry
                   if r.get('config_entry_id') == entry['entry_id'] and not r.get('disabled_by')
                   and r.get('entity_id', '').startswith('sensor.') and r['entity_id'] in states]
        if not sensors or any(s.get('state') not in ('unknown', 'unavailable') for s in sensors):
            continue
        # Allow normal startup to finish before trying discovery.
        from datetime import datetime
        try:
            if any(now - datetime.fromisoformat(s['last_changed'].replace('Z', '+00:00')).timestamp() < 120 for s in sensors):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        candidates.append(entry)
    if not candidates:
        return []
    adapters = current_adapters(ws({'type': 'network'}).get('adapters', []))
    devices = discover(adapters)['devices']
    # UDP-disabled loggers: read their immutable identity, never infer it from a port.
    unidentified = [d for d in devices if d.get('status') == 'unidentified'][:8]
    for serial in sorted({e['options']['logger_serial'] for e in candidates})[:8]:
        for device in unidentified:
            found = identify(device['host'], serial)
            if found and found['loggerSerial'] == serial:
                devices.append({**found, 'host':device['host'], 'connector':'solarman',
                                'status':'found', 'identityVerified':True})
    results = []
    for entry in candidates:
        options = entry['options']
        host = replacement(options, devices, adapters)
        if not host:
            continue
        # Re-read to avoid overwriting a concurrent installer edit.
        current = json.loads((config / '.storage/core.config_entries').read_text())['data']['entries']
        if not any(e == entry for e in current):
            continue
        flow = call('/config/config_entries/options/flow', method='POST', payload={'handler': entry['entry_id']})
        flow_id = flow.get('flow_id', '')
        if flow.get('type') != 'form' or flow.get('step_id') != 'init' or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', flow_id):
            continue
        result = call('/config/config_entries/options/flow/' + flow_id, method='POST', payload={**options, 'host': host})
        if result.get('type') == 'create_entry':
            results.append({'entryId': entry['entry_id'], 'host': host})
    return results
