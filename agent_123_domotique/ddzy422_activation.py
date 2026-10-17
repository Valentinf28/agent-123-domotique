"""Explicit native-reader activation; a readiness poll can never restart HA."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
from ddzy422_setup import DOMAIN, verify_bundle

COOLDOWN = 300

def activate(payload, call, *, loaded_manifest, authorize, config=Path('/homeassistant_config'), data=Path('/data'), now=None):
    owner=payload.get('ownerScope');operation=payload.get('operation')
    if not isinstance(owner,str) or not re.fullmatch('[a-f0-9]{64}',owner) or operation not in ('status','activate'):
        raise ValueError('La demande d’activation doit être vérifiée.')
    if operation=='activate' and payload.get('confirmed') is not True:
        raise ValueError('Confirmez l’interruption temporaire de Home Assistant avant son activation.')
    config,data=Path(config),Path(data);now=time.time() if now is None else now
    if config.is_symlink() or (config/'custom_components').is_symlink():raise RuntimeError('Le dossier du connecteur doit être vérifié.')
    target=config/'custom_components'/DOMAIN
    if target.is_symlink():raise RuntimeError('Un connecteur tiers est conservé.')
    bundle=verify_bundle()
    for name,checksum in bundle['files'].items():
        path=target/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
            raise RuntimeError('Le connecteur local doit être préparé avant son activation. Les fichiers existants sont conservés.')
    journal=data/'ddzy422-activation.json'
    # Status reads no private owner information and does not create a journal,
    # lock or directory. Activation rechecks readiness inside its OS lock.
    def state():return json.loads(journal.read_text()) if journal.exists() else {}
    def pending(value):
        requested=value.get('requestedAt')
        return type(requested) in (int,float) and now-requested<COOLDOWN
    def response(status,value=None):
        result={'connector':DOMAIN,'status':status,'configured':False}
        if status=='activation_pending':
            requested=value['requestedAt'];result.update(requestedAt=requested,retryAfterSeconds=max(1,min(COOLDOWN,int(COOLDOWN-(now-requested)))))
        return result
    def readiness(value):
        try:handlers=call('/config/config_entries/flow_handlers')
        except (TimeoutError,urllib.error.URLError,ConnectionError):
            if pending(value):return response('activation_pending',value)
            raise RuntimeError('Le chargement du connecteur ne peut pas encore être vérifié.') from None
        if not isinstance(handlers,list):raise RuntimeError('La liste des connecteurs est indisponible.')
        if (DOMAIN in handlers and isinstance(loaded_manifest,dict) and loaded_manifest.get('domain')==DOMAIN
                and loaded_manifest.get('version')==bundle['version'] and loaded_manifest.get('is_built_in') is False):
            return response('ready')
        if pending(value):return response('activation_pending',value)
        return response('restart_required')
    if operation=='status':return readiness(state())
    data.mkdir(exist_ok=True,parents=True)
    descriptor=os.open(data/'ddzy422-activation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=state();result=readiness(current)
        if result['status']!='restart_required':return result
        try:user=authorize()
        except Exception:user=None
        if not isinstance(user,dict) or user.get('is_admin') is not True:
            raise RuntimeError('La box ne dispose pas des droits Home Assistant nécessaires à cette activation.')
        temporary=journal.with_suffix('.tmp');descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        current={'requestedAt':now,'ownerScope':owner}
        with os.fdopen(descriptor,'w') as file:json.dump(current,file);file.flush();os.fsync(file.fileno())
        temporary.replace(journal)
        descriptor=os.open(data,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        try:call('/services/homeassistant/restart',method='POST',payload={},timeout=15)
        except urllib.error.HTTPError as error:
            if error.code in (400,401,403,404,405):
                journal.unlink(missing_ok=True)
                raise RuntimeError('L’activation a été refusée par Home Assistant. Aucun nouvel essai automatique n’est effectué.') from None
            # A 5xx response during service shutdown does not prove a refusal.
        except (TimeoutError,urllib.error.URLError,ConnectionError):
            pass
        return response('activation_pending',current)
