"""Confirm only native HA Lektrico zeroconf flows; never scan or control a charger."""
import re

ACTION = 'commissioning.lektrico'
ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
OWNER = re.compile(r'^[a-f0-9]{64}$')
SERIAL = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def _entries(call):
    rows = call('/config/config_entries/entry?domain=lektrico')
    if not isinstance(rows, list):
        raise RuntimeError('Connexions non vérifiées.')
    return [{'entryId': row['entry_id'], 'state': row.get('state', 'unknown'), 'disabled': bool(row.get('disabled_by'))}
            for row in rows if isinstance(row, dict) and row.get('domain') == 'lektrico'
            and isinstance(row.get('entry_id'), str) and ID.fullmatch(row['entry_id'])]


def _discovered(registry):
    rows = registry({'type': 'config_entries/flow/progress'})
    if not isinstance(rows, list):
        raise RuntimeError('Découvertes non vérifiées.')
    result = []
    for row in rows[:200]:
        if not isinstance(row, dict) or row.get('handler') != 'lektrico' or row.get('step_id') != 'confirm':
            continue
        context = row.get('context', {})
        if not isinstance(context, dict) or context.get('source') != 'zeroconf':
            continue
        title = context.get('title_placeholders', {})
        serial = title.get('serial_number') if isinstance(title, dict) else None
        flow_id = row.get('flow_id')
        if isinstance(serial, str) and SERIAL.fullmatch(serial) and isinstance(flow_id, str) and ID.fullmatch(flow_id):
            result.append({'flowId': flow_id, 'serial': serial, 'name': str(title.get('name', 'Lektrico'))[:120]})
    return result


def _devices(entries, call, registry, domain='lektrico'):
    ids = {row['entryId'] for row in entries if not row['disabled']}
    devices = registry({'type': 'config/device_registry/list'})
    entities = registry({'type': 'config/entity_registry/list'})
    states = call('/states')
    if not all(isinstance(rows, list) for rows in (devices, entities, states)):
        raise RuntimeError('Appareils non vérifiés.')
    legacy_devices = {row.get('device_id') for row in entities if isinstance(row, dict) and domain == 'keba' and row.get('platform') == domain and not row.get('config_entry_id')}
    state_map = {row.get('entity_id'): row for row in states if isinstance(row, dict)}
    result = []
    for device in devices[:500]:
        if not isinstance(device, dict) or not (ids.intersection(device.get('config_entries', [])) or device.get('id') in legacy_devices):
            continue
        serials = [pair[1] for pair in device.get('identifiers', []) if isinstance(pair, (list, tuple)) and len(pair) == 2
                   and pair[0] == domain and isinstance(pair[1], str) and SERIAL.fullmatch(pair[1])]
        if (domain == 'lektrico' and len(serials) != 1) or not isinstance(device.get('id'), str) or not ID.fullmatch(device['id']):
            continue
        exposed = []
        for entity in entities[:5000]:
            if not isinstance(entity, dict) or entity.get('device_id') != device['id'] or (entity.get('config_entry_id') not in ids and not (domain == 'keba' and not entity.get('config_entry_id'))) or entity.get('platform') != domain or entity.get('disabled_by'):
                continue
            entity_id = entity.get('entity_id', '')
            if not isinstance(entity_id, str) or not re.fullmatch(r'(sensor|binary_sensor|switch|number|select|button)\.[a-z0-9_]{1,180}', entity_id):
                continue
            state = state_map.get(entity_id, {})
            attrs = state.get('attributes', {})
            attrs = attrs if isinstance(attrs, dict) else {}
            raw = str(state.get('state', 'unavailable'))[:80]
            exposed.append({'id': entity_id, 'name': str(attrs.get('friendly_name') or entity_id)[:120],
                            'domain': entity_id.split('.')[0], 'state': raw, 'available': raw not in ('unknown', 'unavailable', ''),
                            'unit': str(attrs.get('unit_of_measurement', ''))[:20]})
        result.append({'id': device['id'], 'serial': serials[0] if len(serials) == 1 else '', 'name': str(device.get('name_by_user') or device.get('name') or domain)[:120],
                       'brand': str(device.get('manufacturer') or domain)[:80], 'model': str(device.get('model') or 'À identifier')[:120], 'room': '', 'entities': exposed[:60]})
    return result[:100]


def configure(payload, call, *, registry):
    if not isinstance(payload, dict) or not OWNER.fullmatch(str(payload.get('ownerScope', ''))):
        raise ValueError('Propriétaire non vérifié.')
    operation = payload.get('operation')
    if operation not in ('status', 'confirm'):
        raise ValueError('Opération inconnue.')
    expected = {'operation','ownerScope'} if operation == 'status' else {'operation','ownerScope','flowId','serial','identityConfirmed'}
    if set(payload) != expected:
        raise ValueError('Paramètres inconnus.')
    entries = _entries(call)
    devices = _devices(entries, call, registry)
    discovered = _discovered(registry)
    if operation == 'confirm':
        serial, flow_id = payload.get('serial'), payload.get('flowId')
        if payload.get('identityConfirmed') is not True or not isinstance(serial, str) or not SERIAL.fullmatch(serial) or not isinstance(flow_id, str) or not ID.fullmatch(flow_id):
            raise ValueError('Confirmez la référence réelle de cette borne.')
        # Native serial identity survives a lost confirmation response; never create a duplicate.
        existing = [device for device in devices if device['serial'] == serial]
        if len(existing) > 1:
            raise RuntimeError('Identité ambiguë.')
        if not existing:
            candidates = [row for row in discovered if row['flowId'] == flow_id and row['serial'] == serial]
            if len(candidates) != 1:
                raise ValueError('Découverte expirée ou identité différente.')
            flow = call('/config/config_entries/flow/' + flow_id)
            if not isinstance(flow, dict) or flow.get('handler') != 'lektrico' or flow.get('type') != 'form' or flow.get('step_id') != 'confirm' or flow.get('errors'):
                raise RuntimeError('Formulaire natif non confirmé.')
            reply = call('/config/config_entries/flow/' + flow_id, method='POST', payload={})
            if not isinstance(reply, dict) or reply.get('type') != 'create_entry':
                raise RuntimeError('Connexion non confirmée ; actualisez.')
            entries = _entries(call)
            devices = _devices(entries, call, registry)
            discovered = _discovered(registry)
            if len([device for device in devices if device['serial'] == serial]) != 1:
                raise RuntimeError('La borne configurée n’est pas encore identifiable ; actualisez.')
    return {'connector': 'lektrico', 'status': 'existing' if entries else 'not_configured',
            'devicesVerified': False, 'entries': entries, 'discoveries': discovered, 'devices': devices}
