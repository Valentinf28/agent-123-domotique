"""Native HA Tuya login over a live channel. Never stores user codes or tokens.

Only our nonce-bound flow is editable. Existing entries are always preserved.
HA owns authentication, QR issuance, token storage and device import.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import time
import urllib.error

ACTION = 'commissioning.tuya'
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
SESSION = re.compile(r'^[a-f0-9-]{36}$')
OWNER = re.compile(r'^[a-f0-9]{64}$')
TTL = 600


def _entries(call):
    rows = call('/config/config_entries/entry?domain=tuya')
    if not isinstance(rows, list):
        raise RuntimeError('Les connexions Tuya ne peuvent pas être vérifiées.')
    return [{'entryId': row['entry_id'], 'state': row.get('state', 'unknown'),
             'disabled': bool(row.get('disabled_by'))}
            for row in rows if isinstance(row, dict) and row.get('domain') == 'tuya'
            and isinstance(row.get('entry_id'), str) and SAFE_ID.fullmatch(row['entry_id'])]


def _devices(entries, call, registry, membership=None):
    if registry is None:
        return []
    ids = {entry['entryId'] for entry in entries if not entry['disabled']}
    entities = registry({'type':'config/entity_registry/list'})
    devices = registry({'type':'config/device_registry/list'})
    areas = registry({'type':'config/area_registry/list'})
    states = call('/states')
    if not all(isinstance(rows, list) for rows in (entities, devices, areas, states)):
        raise RuntimeError('Les appareils Tuya ne peuvent pas encore être vérifiés.')
    device_map = {row.get('id'):row for row in devices if isinstance(row, dict)}
    area_map = {row.get('area_id'):str(row.get('name',''))[:80] for row in areas if isinstance(row, dict)}
    state_map = {row.get('entity_id'):row for row in states if isinstance(row, dict)}
    groups = {}
    for entity in entities:
        if not isinstance(entity, dict) or entity.get('config_entry_id') not in ids or entity.get('platform') != 'tuya' or entity.get('disabled_by'):
            continue
        entity_id = entity.get('entity_id', '')
        if not isinstance(entity_id, str) or not re.fullmatch(r'[a-z_]+\.[a-z0-9_]{1,180}', entity_id):
            continue
        domain = entity_id.split('.')[0]
        if domain in ('lock', 'remote'):
            continue
        raw_device = device_map.get(entity.get('device_id'), {})
        raw_state = state_map.get(entity_id, {})
        attributes = raw_state.get('attributes', {})
        if not isinstance(attributes, dict):
            attributes = {}
        device_id = entity.get('device_id') or entity_id
        if not isinstance(device_id, str) or len(device_id) > 200:
            continue
        name = str(raw_device.get('name_by_user') or raw_device.get('name') or attributes.get('friendly_name') or entity_id)[:120]
        group = groups.setdefault(device_id, {'id':device_id,'name':name,
            'brand':str(raw_device.get('manufacturer') or 'Tuya')[:80],
            'model':str(raw_device.get('model') or 'Appareil Smart Life')[:120],
            'room':area_map.get(raw_device.get('area_id'), ''), 'homeIds':[], 'entities':[]})
        for identifier in raw_device.get('identifiers', []):
            if isinstance(identifier, (list, tuple)) and len(identifier) == 2 and identifier[0] == 'tuya':
                for home_id in (membership or {}).get((entity['config_entry_id'], identifier[1]), []):
                    if home_id not in group['homeIds']:
                        group['homeIds'].append(home_id)
        state = str(raw_state.get('state', 'unavailable'))[:80]
        group['entities'].append({'id':entity_id,'name':str(attributes.get('friendly_name') or entity_id)[:120],
            'domain':domain,'state':state,'available':state.lower() not in ('unknown','unavailable',''),
            'unit':str(attributes.get('unit_of_measurement') or '')[:20]})
    for group in groups.values():
        group['entities'] = group['entities'][:60]
    return list(groups.values())[:100]


def _view(entries, call=None, registry=None, homes_reader=None):
    homes, membership, status = [], {}, 'unavailable'
    if entries and homes_reader is not None:
        try:
            homes, membership = homes_reader(entries)
            status = 'ready'
        except Exception:
            # No SDK/credential errors or exception strings leave the box.
            pass
    return {'connector': 'tuya', 'status': 'existing' if entries else 'not_configured',
            'entries': entries, 'devicesVerified': False, 'homesStatus':status, 'homes':homes,
            'devices':_devices(entries, call, registry, membership) if entries else []}


def _form(flow):
    if not isinstance(flow, dict) or flow.get('handler') not in (None, 'tuya'):
        raise RuntimeError('Le formulaire reçu ne correspond pas à Tuya.')
    if flow.get('type') == 'abort':
        return {'connector': 'tuya', 'status': 'aborted', 'devicesVerified': False}
    if flow.get('type') != 'form' or flow.get('step_id') not in ('user', 'scan'):
        raise RuntimeError('Cette version du formulaire Tuya nécessite une vérification.')
    result = {'connector': 'tuya', 'status': 'user_code' if flow['step_id'] == 'user' else 'scan',
              'devicesVerified': False, 'retry': bool(flow.get('errors'))}
    if flow['step_id'] == 'scan':
        fields = flow.get('data_schema', [])
        if not isinstance(fields, list):
            raise RuntimeError('Le QR Tuya n’est pas disponible.')
        codes = [field.get('selector', {}).get('qr_code', {}).get('data')
                 for field in fields if isinstance(field, dict) and field.get('name') == 'QR']
        if len(codes) != 1 or not isinstance(codes[0], str) or not re.fullmatch(
                r'tuyaSmart--qrLogin\?token=[A-Za-z0-9._~%+=/-]{1,2048}', codes[0]):
            raise RuntimeError('Le QR Tuya reçu ne peut pas être affiché.')
        result['qrData'] = codes[0]
    return result


def configure(payload, call, *, data=Path('/data'), now=None, registry=None, homes_reader=None):
    """Allowed operations: status/start/code/confirm/cancel/reload.

    The portal supplies ownerScope, never the browser. Session nonce stays only
    in browser memory. File contains flow id/nonce/expiry, no HA response bodies.
    """
    now = time.time() if now is None else now
    operation = payload.get('operation')
    if operation not in ('status', 'start', 'code', 'confirm', 'cancel', 'reload'):
        raise ValueError('Étape Tuya inconnue.')
    owner, session = payload.get('ownerScope', ''), payload.get('session', '')
    if not isinstance(owner, str) or not OWNER.fullmatch(owner):
        raise ValueError('La maison de cette connexion doit être vérifiée.')
    if operation not in ('status', 'reload') and (not isinstance(session, str) or not SESSION.fullmatch(session)):
        raise ValueError('Session de connexion invalide.')
    data = Path(data); data.mkdir(exist_ok=True)
    descriptor = os.open(data / 'tuya-flow.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        journal = data / 'tuya-flow.json'
        state = json.loads(journal.read_text()) if journal.exists() else {}
        def save(value):
            temporary = journal.with_suffix('.tmp')
            fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream)
            temporary.replace(journal)
        entries = _entries(call)
        if operation == 'status':
            return _view(entries, call, registry, homes_reader)
        if operation == 'reload':
            entry_id = payload.get('entryId')
            selected = next((entry for entry in entries if entry['entryId'] == entry_id), None)
            if not selected or selected['disabled']:
                raise ValueError('Choisissez une connexion Tuya active de cette box.')
            # Native integration reload imports new devices; no service action.
            call(f'/config/config_entries/entry/{entry_id}/reload', method='POST', payload={})
            return _view(_entries(call), call, registry, homes_reader)
        # Expired guided logins may be abandoned by a refreshed browser or a
        # former owner. Only start can retire an expired known Tuya flow; never
        # resumes or confirms it. A lost *start* had not received any User Code.
        if operation == 'start' and state and now >= state.get('expiresAt', 0):
            stale_id = state.get('flowId')
            if isinstance(stale_id, str) and SAFE_ID.fullmatch(stale_id):
                try:
                    call(f'/config/config_entries/flow/{stale_id}', method='DELETE')
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
            elif not state.get('starting'):
                raise RuntimeError('La session expirée doit être vérifiée par l’équipe.')
            save({})
            state = {}
        if state and (state.get('ownerScope') != owner or state.get('session') != session):
            # Even an expired foreign lease is not resumed, confirmed or deleted.
            raise RuntimeError('Une autre session Tuya est en cours. Reprenez depuis son écran ou contactez l’équipe.')
        flow_id = state.get('flowId')
        if flow_id is not None and (not isinstance(flow_id, str) or not SAFE_ID.fullmatch(flow_id)):
            raise RuntimeError('La session Tuya enregistrée doit être vérifiée.')
        if operation == 'cancel':
            if state.get('starting') and not flow_id:
                raise RuntimeError('Le résultat du démarrage doit être vérifié avant de libérer cette session.')
            if flow_id:
                try:
                    call(f'/config/config_entries/flow/{flow_id}', method='DELETE')
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
            save({})
            return {'connector':'tuya', 'status':'cancelled', 'devicesVerified':False}
        if state and now >= state.get('expiresAt', 0):
            raise RuntimeError('Le délai de cette connexion est écoulé. Annulez cette session puis recommencez.')
        if operation == 'start' and entries:
            return _view(entries, call, registry, homes_reader)
        if operation == 'start' and not state:
            # Persist before HA call. A lost response must not start another flow.
            state = {'ownerScope':owner, 'session':session, 'expiresAt':now+TTL, 'starting':True}
            save(state)
            flow = call('/config/config_entries/flow', method='POST',
                        payload={'handler':'tuya','show_advanced_options':False})
            flow_id = flow.get('flow_id') if isinstance(flow, dict) else None
            if not isinstance(flow_id, str) or not SAFE_ID.fullmatch(flow_id):
                raise RuntimeError('La création du formulaire Tuya n’a pas été confirmée.')
            state = {'ownerScope':owner, 'session':session, 'expiresAt':now+TTL, 'flowId':flow_id}
            save(state)
            return _form(flow)
        if not flow_id:
            raise RuntimeError('Le résultat du démarrage doit être vérifié avant une nouvelle connexion.')
        flow = call(f'/config/config_entries/flow/{flow_id}')
        if not isinstance(flow, dict) or flow.get('flow_id') != flow_id or flow.get('handler') not in (None, 'tuya'):
            raise RuntimeError('Le formulaire Tuya ne correspond plus à votre session.')
        if operation == 'start':
            return _form(flow)
        expected = 'user' if operation == 'code' else 'scan'
        if flow.get('type') != 'form' or flow.get('step_id') != expected:
            raise RuntimeError('Cette étape Tuya a changé. Reprenez la connexion depuis le même écran.')
        values = {}
        if operation == 'code':
            code = payload.get('userCode')
            if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', code):
                raise ValueError('Recopiez le User Code affiché dans Smart Life ou Tuya Smart.')
            values = {'user_code':code}
        result = call(f'/config/config_entries/flow/{flow_id}', method='POST', payload=values)
        if isinstance(result, dict) and result.get('type') == 'create_entry':
            entry = result.get('result', {})
            entry_id = entry.get('entry_id') if isinstance(entry, dict) else None
            actual = _entries(call)
            if not entry_id or not any(row['entryId'] == entry_id for row in actual):
                raise RuntimeError('La connexion Tuya créée n’a pas encore été confirmée par la box.')
            save({})
            return {**_view(actual,call,registry,homes_reader), 'status':'configured'}
        return _form(result)
