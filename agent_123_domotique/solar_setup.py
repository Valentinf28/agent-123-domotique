"""Create one explicit read-only Deye connection through HA's config flow.

Never edits HA storage, existing integration entries, or inverter registers.
"""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import urllib.error
from network_discovery import local_interfaces
from solar_profile import PROFILE


def settings(payload, adapters):
    try:
        host = ipaddress.IPv4Address(payload.get('host', ''))
    except (ValueError, TypeError):
        raise ValueError('Adresse locale du boîtier solaire invalide.') from None
    interfaces = local_interfaces(adapters)
    if not any(host in interface.network and host not in
               (interface.ip, interface.network.network_address, interface.network.broadcast_address)
               for interface in interfaces):
        raise ValueError('Le boîtier solaire doit être sur le réseau local de cette box.')
    serial = payload.get('loggerSerial')
    if type(serial) is not int or not 0 < serial <= 0xffffffff:
        raise ValueError('Numéro du boîtier solaire invalide.')
    if payload.get('model') != 'deye_sg01hp3':
        raise ValueError('Ce modèle nécessite un autre profil de connexion.')
    return {'name': f'1.2.3 Home Deye {serial}', 'host': str(host), 'port': 8899,
            'transport': 'tcp', 'logger_serial': serial,
            'lookup_file': f'custom/{PROFILE}', 'additional_options': {'mod': 1}}


def configure(payload, adapters, call, *, config=Path('/homeassistant_config'), data=Path('/data')):
    values = settings(payload, adapters)
    config, data = Path(config), Path(data)
    root = config / 'custom_components/solarman'
    if not (root / '123home-bundle.json').is_file():
        raise RuntimeError('Le connecteur guidé doit être préparé avant la connexion. Un connecteur existant est conservé.')
    data.mkdir(exist_ok=True)
    lock = os.open(data / 'solar-setup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock,'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        # Read persisted options solely to avoid modifying/duplicating another setup.
        storage = json.loads((config / '.storage/core.config_entries').read_text())
        stored = storage['data']['entries']
        live = call('/config/config_entries/entry?domain=solarman')
        if not isinstance(live,list):
            raise RuntimeError('Impossible de vérifier les connexions solaires existantes.')
        candidates = [entry for entry in stored if entry.get('domain') == 'solarman']
        own = [entry for entry in live if entry.get('title') == values['name']]
        matching = [entry for entry in candidates if entry.get('options',{}).get('host') == values['host']
                    or entry.get('options',{}).get('logger_serial') == values['logger_serial']]
        if matching:
            if len(matching) != 1 or any(matching[0].get('options',{}).get(k) != values[k]
                                       for k in ('host','logger_serial','lookup_file')):
                raise RuntimeError('Ce boîtier possède déjà une connexion différente. Elle a été conservée ; une vérification est nécessaire.')
            if matching[0].get('options', {}).get('additional_options', {}).get('mod') != 1:
                raise RuntimeError('Le profil haute tension de cette connexion doit être corrigé avant validation.')
            if matching[0]['entry_id'] not in {entry['entry_id'] for entry in live}:
                raise RuntimeError('La connexion enregistrée n’est plus active. Vérification nécessaire.')
            return {'connector':'solarman','status':'configured','entryId':matching[0]['entry_id'], 'measurementsVerified':False}
        if own or any(entry['entry_id'] not in {row['entry_id'] for row in candidates} for entry in live):
            raise RuntimeError('Une connexion solaire est en cours d’enregistrement. Réessayez dans quelques instants.')
        journal = data / f'solar-{values["logger_serial"]}.json'
        state = json.loads(journal.read_text()) if journal.exists() else {}
        if state and state.get('settings') != values:
            raise RuntimeError('Une autre configuration de ce boîtier est déjà en cours. Vérification nécessaire.')
        def save(value):
            temp = journal.with_suffix('.tmp')
            temp.write_text(json.dumps({'settings':values, **value}))
            temp.chmod(0o600)
            temp.replace(journal)
        flow_id = state.get('flowId')
        if state.get('submitted'):
            # Resume only the original flow, never create a second one after a lost response.
            if not isinstance(flow_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', flow_id):
                raise RuntimeError('La demande a déjà été envoyée. Son résultat doit être vérifié avant de créer une autre connexion.')
            try:
                progress = call(f'/config/config_entries/flow/{flow_id}')
            except urllib.error.HTTPError:
                raise RuntimeError('La demande a déjà été envoyée. Son résultat doit être vérifié avant de créer une autre connexion.') from None
            if not isinstance(progress, dict) or progress.get('type') != 'form' or progress.get('step_id') != 'user' or progress.get('flow_id') != flow_id:
                raise RuntimeError('La demande a déjà été envoyée. Son résultat doit être vérifié avant de créer une autre connexion.')
            save({'flowId':flow_id})
        elif flow_id:
            # A refused/unsubmitted form may disappear on a core restart. Only this
            # known-unsubmitted case may start a replacement after an explicit 404.
            try:
                progress = call(f'/config/config_entries/flow/{flow_id}')
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                flow_id = None
                save({})
            else:
                if not isinstance(progress, dict) or progress.get('type') != 'form' or progress.get('step_id') != 'user' or progress.get('flow_id') != flow_id:
                    raise RuntimeError('Le formulaire solaire ne peut pas encore être repris. Vérification nécessaire.')
        if not flow_id:
            flow = call('/config/config_entries/flow',method='POST',payload={'handler':'solarman','show_advanced_options':False})
            flow_id = flow.get('flow_id')
            if flow.get('type') != 'form' or flow.get('step_id') != 'user' or not isinstance(flow_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',flow_id):
                raise RuntimeError('Le connecteur solaire n’est pas prêt à recevoir la configuration.')
            save({'flowId':flow_id})
        # Persist before submission: a lost HTTP response must never create a duplicate.
        save({'flowId':flow_id,'submitted':True})
        try:
            result = call(f'/config/config_entries/flow/{flow_id}',method='POST',payload=values)
        except urllib.error.HTTPError as error:
            if error.code != 400:
                raise
            # HA's explicit schema rejection has not created an entry. Keep the same flow.
            save({'flowId':flow_id})
            try:
                body = json.loads(error.read(8192))
                errors = body.get('errors', {})
                fields = ', '.join(sorted(key for key in errors if key in values)) if isinstance(errors, dict) else ''
            except (ValueError, TypeError, AttributeError):
                fields = ''
            raise RuntimeError('Le formulaire solaire refuse ces paramètres' + (': ' + fields if fields else '') + '. La demande peut être corrigée puis reprise sans doublon.') from None
        if result.get('type') == 'form':
            save({'flowId':flow_id})
            raise RuntimeError('La configuration a été refusée. Vérifiez l’adresse et le numéro du boîtier.')
        entry = result.get('result',{})
        if result.get('type') != 'create_entry' or not isinstance(entry,dict) or not entry.get('entry_id'):
            raise RuntimeError('La création de la connexion n’a pas été confirmée. Vérification nécessaire.')
        save({'flowId':flow_id,'submitted':True,'entryId':entry['entry_id']})
        return {'connector':'solarman','status':'configured','entryId':entry['entry_id'],'measurementsVerified':False}
