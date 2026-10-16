"""Install only our pinned native local-reader bundle; connect via HA config flow."""
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from network_discovery import local_interfaces

DOMAIN = 'labox_ddzy422'
BUNDLE = Path(__file__).parent / 'integrations' / DOMAIN
BUNDLE_INDEX = Path(__file__).parent / 'integrations' / 'ddzy422-bundle.json'
BUNDLE_SHA256 = 'df4d7820c57a1fc10dd4dff4ec8edc170432822dd0bb419aaa727a6ebb18d05d'
LEGACY_INDEX = Path(__file__).parent / 'integrations' / 'ddzy422-legacy-010.json'
LEGACY_INDEX_SHA256 = '034e0d3d2120dcd2b1be83a895da6678598ea9859e2e3bcbf99ea04185f394bd'
FILES = frozenset(('__init__.py','config_flow.py','const.py','coordinator.py','manifest.json','sensor.py','strings.json','transport.py','PROTOCOL.md'))

def verify_bundle(bundle=BUNDLE, index=BUNDLE_INDEX):
    bundle,index=Path(bundle),Path(index)
    if index.is_symlink() or hashlib.sha256(index.read_bytes()).hexdigest()!=BUNDLE_SHA256:
        raise RuntimeError('L’inventaire du connecteur local est altéré.')
    values=json.loads(index.read_text())
    if values.get('domain')!=DOMAIN or set(values.get('files',{}))!=FILES:
        raise RuntimeError('Le connecteur local fourni doit être vérifié.')
    actual={}
    for name in FILES:
        path=bundle/name
        if bundle.is_symlink() or path.is_symlink() or not path.is_file():raise RuntimeError('Dossier du connecteur local invalide.')
        actual[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=values['files']:raise RuntimeError('Le connecteur local fourni est altéré.')
    return values

def install(config=Path('/homeassistant_config'), bundle=BUNDLE, index=BUNDLE_INDEX):
    config,bundle,index=Path(config),Path(bundle),Path(index)
    if not config.is_dir() or config.is_symlink():raise RuntimeError('La configuration de la box est inaccessible.')
    components=config/'custom_components'
    if components.is_symlink():raise RuntimeError('Le dossier des connecteurs doit être vérifié.')
    components.mkdir(exist_ok=True)
    fd=os.open(config/'.123home-ddzy422-install.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        manifest=verify_bundle(bundle,index)
        target=components/DOMAIN
        if target.is_symlink():raise RuntimeError('Une installation différente du connecteur est conservée.')
        upgrading = False
        if target.exists():
            def matches(files):
                return all(not (target/name).is_symlink() and (target/name).is_file()
                           and hashlib.sha256((target/name).read_bytes()).hexdigest()==checksum
                           for name,checksum in files.items())
            # HA scans every directory inside custom_components, including hidden backups.
            # Retire the exact known snapshot made by 0.6.13 outside that loader tree.
            misplaced=components/'.123home-ddzy422-previous-010'
            archive=config/'.123home-managed-backups'
            if archive.is_symlink():raise RuntimeError('Le dossier de sauvegarde doit être vérifié.')
            if misplaced.exists() or misplaced.is_symlink():
                if misplaced.is_symlink() or LEGACY_INDEX.is_symlink() or hashlib.sha256(LEGACY_INDEX.read_bytes()).hexdigest()!=LEGACY_INDEX_SHA256:
                    raise RuntimeError('La copie précédente du connecteur est conservée.')
                previous_files=json.loads(LEGACY_INDEX.read_text())['files']
                if any((misplaced/name).is_symlink() or not (misplaced/name).is_file() or hashlib.sha256((misplaced/name).read_bytes()).hexdigest()!=checksum for name,checksum in previous_files.items()) or any(p.name not in FILES|{'__pycache__'} for p in misplaced.iterdir()):
                    raise RuntimeError('La copie précédente du connecteur est conservée.')
                archive.mkdir(exist_ok=True,mode=0o700)
                saved=archive/'labox_ddzy422-0.1.0'
                if saved.exists() or saved.is_symlink():raise RuntimeError('La copie précédente existe déjà ; elle est conservée.')
                misplaced.rename(saved)
            if matches(manifest['files']):
                return {'connector':DOMAIN,'status':'existing_preserved','restartRequired':True,'configured':False}
            if LEGACY_INDEX.is_symlink() or hashlib.sha256(LEGACY_INDEX.read_bytes()).hexdigest()!=LEGACY_INDEX_SHA256:
                raise RuntimeError('L’inventaire précédent du connecteur est altéré.')
            legacy=json.loads(LEGACY_INDEX.read_text())
            if set(legacy['files'])!=FILES or not matches(legacy['files']) or any(p.name not in FILES|{'__pycache__'} for p in target.iterdir()):
                raise RuntimeError('Une installation différente du connecteur est conservée.')
            upgrading = True
        staging=Path(tempfile.mkdtemp(prefix='.123home-ddzy422-',dir=components))
        try:
            for name in FILES:
                shutil.copyfile(bundle/name,staging/name);(staging/name).chmod(0o644)
            staging.chmod(0o755)
            if upgrading:
                archive=config/'.123home-managed-backups'
                if archive.is_symlink():raise RuntimeError('Le dossier de sauvegarde doit être vérifié.')
                archive.mkdir(exist_ok=True,mode=0o700)
                previous=archive/'labox_ddzy422-0.1.0'
                if previous.exists():
                    raise RuntimeError('La précédente migration du compteur doit être vérifiée.')
                target.rename(previous)
                try:staging.rename(target)
                except BaseException:
                    previous.rename(target);raise
            else:staging.rename(target)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return {'connector':DOMAIN,'status':'installed','version':manifest['version'],'restartRequired':True,'configured':False}

def configure(payload,adapters,call,*,config=Path('/homeassistant_config'),data=Path('/data')):
    host=payload.get('host');serial=payload.get('loggerSerial');mac=payload.get('mac')
    try:ip=ipaddress.IPv4Address(host)
    except (ValueError,TypeError):raise ValueError('Adresse du compteur invalide.') from None
    interfaces=local_interfaces(adapters)
    if not any(ip in interface.network and ip not in (interface.ip,interface.network.network_address,interface.network.broadcast_address) for interface in interfaces):
        raise ValueError('Le compteur doit être sur le réseau local de la box.')
    compact=mac.replace(':','').upper() if isinstance(mac,str) else ''
    if type(serial) is not int or not 0<serial<=0xffffffff or not re.fullmatch('[0-9A-F]{12}',compact) or compact=='000000000000' or int(compact[:2],16)&1:
        raise ValueError('Identité du compteur invalide.')
    values={'host':str(ip),'logger_serial':serial,'mac':compact}
    config=Path(config)
    if config.is_symlink() or (config/'custom_components').is_symlink():raise RuntimeError('Le dossier du connecteur doit être vérifié.')
    target=config/'custom_components'/DOMAIN
    for name,checksum in verify_bundle()['files'].items():
        path=target/name
        if target.is_symlink() or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
            raise RuntimeError('Le connecteur local doit être installé puis chargé par Home Assistant.')
    data=Path(data);data.mkdir(exist_ok=True,parents=True)
    fd=os.open(data/'ddzy422-setup.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        # Read live entries and existing private settings; never mutate HA storage.
        stored=json.loads((Path(config)/'.storage/core.config_entries').read_text())['data']['entries']
        matching=[e for e in stored if e.get('domain')==DOMAIN and str(e.get('unique_id'))==str(serial)]
        live=call('/config/config_entries/entry?domain='+DOMAIN)
        if not isinstance(live,list):raise RuntimeError('Les compteurs configurés ne peuvent pas être vérifiés.')
        if matching:
            if len(matching)!=1 or matching[0].get('data')!=values:raise RuntimeError('Ce compteur possède une autre configuration, conservée.')
            entry=next((e for e in live if e.get('entry_id')==matching[0]['entry_id']),None)
            if not entry or entry.get('disabled_by') or entry.get('state')!='loaded':raise RuntimeError('Le compteur est enregistré mais ses mesures ne sont pas disponibles.')
            return {'connector':DOMAIN,'status':'configured','entryId':entry['entry_id'],'measurementsVerified':False}
        journal=data/f'ddzy422-{serial}.json'
        state=json.loads(journal.read_text()) if journal.exists() else {}
        # Explicit reconfiguration after our verified reset is distinct from a
        # lost creation response. Only the exact removed HA entry retires a flow.
        reset_path = data / 'installation-reset.json'
        reset_state = json.loads(reset_path.read_text()) if reset_path.exists() else {}
        if (state.get('entryId') and reset_state.get('state') == 'completed'
                and state['entryId'] in reset_state.get('removedEntryIds', [])
                and not any(e.get('entry_id') == state['entryId'] for e in live)):
            state = {}

        if state and state.get('settings')!=values:raise RuntimeError('Une autre préparation de ce compteur est conservée.')
        def save(value):
            temporary=journal.with_suffix('.tmp');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as file:json.dump({'settings':values,**value},file);file.flush();os.fsync(file.fileno())
            temporary.replace(journal)
        flow_id=state.get('flowId')
        if flow_id:
            if not isinstance(flow_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',flow_id):raise RuntimeError('La préparation doit être vérifiée.')
            flow=call('/config/config_entries/flow/'+flow_id)
        else:
            flow=call('/config/config_entries/flow',method='POST',payload={'handler':DOMAIN,'show_advanced_options':False})
            flow_id=flow.get('flow_id')
        if not isinstance(flow_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',flow_id) or flow.get('type')!='form' or flow.get('step_id')!='user':
            raise RuntimeError('Le formulaire du compteur est indisponible. Vérifiez le chargement du connecteur.')
        save({'flowId':flow_id,'submitted':True})
        result=call('/config/config_entries/flow/'+flow_id,method='POST',payload=values,timeout=30)
        if result.get('type')!='create_entry' or not isinstance(result.get('result',{}).get('entry_id'),str):
            raise RuntimeError('La lecture locale du compteur n’est pas confirmée. La préparation est conservée.')
        save({'flowId':flow_id,'submitted':True,'entryId':result['result']['entry_id']})
        return {'connector':DOMAIN,'status':'configured','entryId':result['result']['entry_id'],'measurementsVerified':False}
