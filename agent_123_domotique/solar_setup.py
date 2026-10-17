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
from solar_profile import PROFILE, LP1_PROFILE, MICRO_PROFILE, ensure_profile


def settings(payload, adapters, topology=None):
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
    if payload.get('model') not in ('deye_sg01hp3','deye_lp1','deye_micro'):
        raise ValueError('Ce modèle nécessite un autre profil de connexion.')
    if payload['model']=='deye_lp1':
        if (not isinstance(topology,dict) or topology.get('loggerSerial')!=serial
            or type(topology.get('mppt')) is not int or not 1<=topology['mppt']<=4
            or topology.get('phase')!=1 or topology.get('mod')!=0):
            raise ValueError('Les entrées solaires de cet onduleur doivent être lues avant sa connexion.')
    return {'name': f'1.2.3 Home Deye {serial}', 'host': str(host), 'port': 8899,
            'transport': 'tcp', 'logger_serial': serial,
            'lookup_file': 'custom/' + {'deye_lp1':LP1_PROFILE,'deye_sg01hp3':PROFILE,'deye_micro':MICRO_PROFILE}[payload['model']],
            'additional_options': {'mod':0,'phase':1,'mppt':topology['mppt']} if payload['model']=='deye_lp1' else {'mod':1 if payload['model']=='deye_sg01hp3' else 0}}


def configure(payload, adapters, call, *, config=Path('/homeassistant_config'), data=Path('/data'), topology_reader=None):
    # Validate local target before any network read; no default MPPT guess.
    if payload.get('model')=='deye_lp1':
        serial=payload.get('loggerSerial')
        settings(payload, adapters, {'loggerSerial':serial,'mppt':1,'phase':1,'mod':0})
        if topology_reader is None:
            from deye_topology import read as topology_reader
        topology=topology_reader(payload['host'],serial)
    else:topology=None
    values = settings(payload, adapters, topology)
    config, data = Path(config), Path(data)
    root = config / 'custom_components/solarman'
    if not (root / '123home-bundle.json').is_file():
        raise RuntimeError('Le connecteur guidé doit être préparé avant la connexion. Un connecteur existant est conservé.')
    data.mkdir(exist_ok=True)
    lock = os.open(data / 'solar-setup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock,'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ensure_profile(root, values['lookup_file'].split('/')[-1])
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
            if matching[0].get('options', {}).get('additional_options', {}).get('mod',0) != values['additional_options']['mod']:
                raise RuntimeError('Le profil '+('haute tension' if payload['model']=='deye_sg01hp3' else 'basse tension')+' de cette connexion doit être corrigé avant validation.')
            if matching[0].get('disabled_by') or any(entry.get('disabled_by') for entry in live if entry['entry_id']==matching[0]['entry_id']):
                raise RuntimeError('Cette ancienne connexion est désactivée. Elle n’a pas été réactivée automatiquement.')
            if matching[0]['entry_id'] not in {entry['entry_id'] for entry in live}:
                raise RuntimeError('La connexion enregistrée n’est plus active. Vérification nécessaire.')
            if payload['model']=='deye_lp1':
                entry=matching[0]
                additional=entry.get('options',{}).get('additional_options',{})
                if additional.get('mppt',4)!=topology['mppt'] or additional.get('phase')!=1:
                    reconcile_topology(entry, values, call, data)
            return {'connector':'solarman','status':'configured','entryId':matching[0]['entry_id'], 'measurementsVerified':False}
        if own or any(entry['entry_id'] not in {row['entry_id'] for row in candidates} for entry in live):
            raise RuntimeError('Une connexion solaire est en cours d’enregistrement. Réessayez dans quelques instants.')
        journal = data / f'solar-{values["logger_serial"]}.json'
        state = json.loads(journal.read_text()) if journal.exists() else {}
        # Explicit reconfiguration after our verified reset is distinct from a
        # lost creation response. Only the exact removed HA entry retires a flow.
        reset_path = data / 'installation-reset.json'
        reset_state = json.loads(reset_path.read_text()) if reset_path.exists() else {}
        if (state.get('entryId') and reset_state.get('state') == 'completed'
                and state['entryId'] in reset_state.get('removedEntryIds', [])
                and not any(e.get('entry_id') == state['entryId'] for e in live)):
            state = {}

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


def reconcile_topology(entry, values, call, data):
    """Update only our managed connector through HA's native options flow."""
    entry_id=entry['entry_id']
    if not isinstance(entry_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',entry_id):
        raise RuntimeError('Connexion solaire invalide.')
    options=entry['options'].copy()
    options['additional_options']={**options.get('additional_options',{}),**values['additional_options']}
    path=Path(data)/('solar-topology-'+entry_id+'.json')
    state=json.loads(path.read_text()) if path.exists() else {}
    # A lost native reply is reconciled from persisted options on the next call,
    # never repeated while the previous submission remains uncertain.
    if state.get('submitted'):raise RuntimeError('La mise à jour des entrées est encore en cours. Actualisez sans la renvoyer.')
    flow=call('/config/config_entries/options/flow',method='POST',payload={'handler':entry_id,'show_advanced_options':False})
    fid=flow.get('flow_id');fields={f.get('name') for f in flow.get('data_schema',[]) if isinstance(f,dict)}
    if (flow.get('type')!='form' or flow.get('step_id')!='init' or flow.get('handler')!=entry_id
        or not isinstance(fid,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',fid)
        or not {'host','logger_serial','lookup_file','additional_options'}<=fields
        or any(key not in fields for key in options)):
        raise RuntimeError('Le formulaire solaire doit être actualisé avant de corriger ses entrées.')
    # Some HA options omit native default values; fill only reviewed defaults.
    for key,value in (('port',8899),('transport','tcp')):
        if key in fields:options.setdefault(key,value)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'entryId':entry_id,'flowId':fid,'mppt':values['additional_options']['mppt'],'submitted':True}));tmp.chmod(0o600);tmp.replace(path)
    reply=call('/config/config_entries/options/flow/'+fid,method='POST',payload=options)
    if not isinstance(reply,dict) or reply.get('type')!='create_entry':
        if isinstance(reply,dict) and reply.get('type')=='form':
            state={'entryId':entry_id,'submitted':False};path.write_text(json.dumps(state));path.chmod(0o600)
        raise RuntimeError('La correction des entrées solaires n’a pas été confirmée.')
