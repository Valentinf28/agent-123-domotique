"""Workshop handoff after a completed backed-up equipment reset. Never an OS wipe."""
import fcntl,hashlib,json,os,re,shutil,threading,time
from pathlib import Path
from factory_activation import PORTAL
UUID=r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'

def save(path,value):
    temporary=path.with_suffix('.tmp');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as file:json.dump(value,file);file.flush();os.fsync(file.fileno())
    temporary.replace(path);fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def command(payload,reset,supervisor,call,*,data=Path('/data'),restart=True,now=None):
    data=Path(data);now=time.time() if now is None else now;path=data/'factory-stage.json';operation=payload.get('operation')
    if operation not in ('factory_prepare','factory_commit','factory_status') or not isinstance(payload.get('ownerScope'),str) or not re.fullmatch('[a-f0-9]{64}',payload['ownerScope']):raise ValueError('Préparation atelier non autorisée.')
    if not re.fullmatch(UUID,str(payload.get('operationId',''))):raise ValueError('Préparation atelier invalide.')
    descriptor=os.open(data/'factory-stage.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(path.read_text()) if path.exists() else None
        if state and (state['operationId']!=payload['operationId'] or state['ownerScope']!=payload['ownerScope']):raise RuntimeError('Une autre préparation atelier existe.')
        def public():return {key:state[key] for key in ('operationId','factoryId','state','backupSlug','resetOperationId')}
        if operation=='factory_status':
            if not state:raise RuntimeError('Préparation atelier absente.')
            return public()
        if payload.get('confirmed') is not True:raise ValueError('Confirmez la première activation neuve.')
        if operation=='factory_prepare':
            if not re.fullmatch('factory_[a-f0-9]{32}',str(payload.get('factoryId',''))) or not re.fullmatch('[a-f0-9]{64}',str(payload.get('factoryToken',''))):raise ValueError('Identité atelier invalide.')
            if state:
                if state['factoryId']!=payload['factoryId'] or state['factoryToken']!=payload['factoryToken'] or state['resetOperationId']!=payload.get('resetOperationId'):raise RuntimeError('La préparation atelier a changé.')
                if state['state']=='preparing':
                    supervisor('/addons/self/options',method='POST',payload={'options':state['options']})
                    observed=supervisor('/addons/self/info').get('options',{})
                    if any(observed.get(key)!=state['options'][key] for key in ('factory_id','factory_token','portal_url','restore_identity','relay_house_id','relay_token')):raise RuntimeError('Les options atelier ne sont pas confirmées.')
                    state['state']='prepared';save(path,state)
                return public()
            reset.require_admin();previous=reset.load()
            if previous.get('state')!='completed' or previous.get('backupVerified') is not True or previous.get('operationId')!=payload.get('resetOperationId') or previous.get('ownerScope')!=payload['ownerScope']:raise RuntimeError('Terminez la remise à zéro et sa sauvegarde avant la première activation.')
            snapshot=reset.snapshot()
            if snapshot['entries'] or snapshot['automations'] or snapshot['blockedReasons']:raise RuntimeError('La box contient encore des équipements. Recommencez leur retrait depuis le portail.')
            proof=reset.verify_archive(previous['backupSlug'])
            if not isinstance(proof,dict) or proof.get('verified') is not True:raise RuntimeError('La sauvegarde complète doit être vérifiée.')
            # Cloud backup configuration belongs to the former installation, not the prepared unit.
            webdav=[row['entryId'] for row in snapshot['preservedEntries'] if row['domain']=='webdav']
            options=supervisor('/addons/self/info').get('options')
            if not isinstance(options,dict):raise RuntimeError('Les options de cette box sont indisponibles.')
            options.update(portal_url=PORTAL,factory_id=payload['factoryId'],factory_token=payload['factoryToken'],enrollment_code='',restore_identity='',relay_house_id='',relay_token='',pool_camera_enabled=False,pool_camera_url='http://camera-traitement-piscine.local:8081/')
            state={key:payload[key] for key in ('operationId','ownerScope','factoryId','factoryToken','resetOperationId')}
            old_state=json.loads((data/'agent-state.json').read_text())
            if not isinstance(old_state.get('token'),str):raise RuntimeError('L’identité actuelle de la box doit être vérifiée.')
            state.update(state='preparing',previousTokenHash=hashlib.sha256(old_state['token'].encode()).hexdigest(),backupSlug=previous['backupSlug'],options=options,webdavEntries=webdav,expiresAt=now+900)
            save(path,state)
            supervisor('/addons/self/options',method='POST',payload={'options':options})
            observed=supervisor('/addons/self/info').get('options',{})
            if any(observed.get(key)!=options[key] for key in ('factory_id','factory_token','portal_url','restore_identity','relay_house_id','relay_token')):raise RuntimeError('Les options atelier ne sont pas confirmées. Conservez la liaison actuelle.')
            state['state']='prepared';save(path,state);return public()
        if not state:raise RuntimeError('Préparation atelier absente.')
        if state['state']=='committed':return public()
        if state['state'] not in ('prepared','committing') or now>=state['expiresAt']:raise RuntimeError('La préparation atelier doit être vérifiée avant de poursuivre.')
        reset.require_admin()
        if state['state']=='prepared':
            if reset.snapshot()['entries'] or reset.snapshot()['automations']:raise RuntimeError('Des équipements sont réapparus. Aucun accès n’a été retiré.')
            state['state']='committing';save(path,state)
        entries=call('/config/config_entries/entry')
        for identifier in state['webdavEntries']:
            if any(e.get('entry_id')==identifier for e in entries):
                response=call('/config/config_entries/entry/'+identifier,method='DELETE')
                if response.get('require_restart') is True:state['haRestartRequired']=True;save(path,state)
        try:call('/states/sensor.home_local_configuration',method='DELETE')
        except Exception:pass  # This display state is not a credential; /data cleanup remains authoritative.
        # The complete backup retains old customer state. The live addon starts with only a new unit identity.
        keep={'options.json','factory-stage.json','factory-stage.lock'}
        for file in data.iterdir():
            if file.name in keep:continue
            if file.is_symlink():raise RuntimeError('Un fichier de données doit être vérifié.')
        for file in data.iterdir():
            if file.name in keep:continue
            if file.is_dir():shutil.rmtree(file)
            else:file.unlink()
        state['state']='committed';state.pop('options',None);state.pop('factoryToken',None);save(path,state)
        if restart:
            def reboot():
                time.sleep(4)
                if state.get('haRestartRequired'):
                    try:call('/services/homeassistant/restart',method='POST',payload={})
                    except Exception:pass
                try:supervisor('/addons/self/restart',method='POST',payload={})
                except Exception:pass  # A lost restart acknowledgement never submits a second request.
            threading.Thread(target=reboot,daemon=True,name='factory-handoff').start()
        return public()


def retired_identity(state,data=Path('/data')):
    journal=Path(data)/'factory-stage.json'
    if not journal.exists():return False
    try:
        staged=json.loads(journal.read_text())
        if staged.get('state') not in ('committing','committed'):return False
        return bool(state.get('pending_enrollment') or (isinstance(state.get('token'),str) and hashlib.sha256(state['token'].encode()).hexdigest()==staged.get('previousTokenHash')))
    except Exception:return True
