"""Owner-consented agent update through HA's first-party update entity.

HA/Supervisor install the current catalog version, not a pinned image. Recheck
latest just before submission; completion requires actual runtime observation.
No installer acknowledgement is considered completion and no submit is replayed.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import uuid
from installation_reset import Reset, _MUTEX, digest, _valid_uuid

TTL=900
SOURCES=('https://github.com/Valentinf28/agent-123-domotique',
         'https://github.com/Valentinf28/agent-123-domotique#codex/automatic-box-relay')
REPOSITORIES={hashlib.sha1(source.lower().encode()).hexdigest()[:8]:source.lower() for source in SOURCES}
_WORKERS={}
_OBSERVERS={}
ACTIVE=frozenset(('refreshing_catalog','backing_up','backup_uncertain','installing','awaiting_restart'))

def version(value,stable=False):
    match=re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-dev([1-9][0-9]*))?',value) if isinstance(value,str) else None
    if not match or stable and match[4] is not None:raise ValueError('La version approuvée doit être une version stable valide.')
    return (*map(int,match.group(1,2,3)),0 if match[4] else 1,int(match[4] or 0))

def busy(data=Path('/data')):
    path=Path(data)/'installation-update.json'
    if not path.exists():return False
    try:return json.loads(path.read_text()).get('state') in ACTIVE
    except Exception:return True

def native_catalog_refresh(call, entity_id):
    """Refresh this native update entity via Core's supported service.

    The add-on WebSocket proxy deliberately refuses supervisor/* commands.
    HA's non-scheduled update-entity refresh reloads the store coordinator.
    No manager role, Supervisor bypass or direct host access is needed.
    """
    if not isinstance(entity_id, str) or not re.fullmatch(r'update\.[a-z0-9_]+', entity_id):
        raise ValueError('Entité de mise à jour invalide.')
    return call('/services/homeassistant/update_entity', method='POST',
                payload={'entity_id': entity_id}, timeout=65)


class Update(Reset):
    backup_name='La Box avant mise à jour '
    def __init__(self,call,supervisor,verify_archive,*,registry,runtime_version,refresh_catalog=None,**kwargs):
        super().__init__(call,supervisor,verify_archive,**kwargs)
        self.path=self.data/'installation-update.json'
        self.registry,self.runtime_version=registry,runtime_version
        self.refresh_catalog=refresh_catalog

    def public(self,state):
        if not state:return {'state':'idle','observedVersion':self.runtime_version}
        keys=('operationId','consentId','targetVersion','releaseCommit','previewHash','expiresAt','state',
              'backupVerified','backupSlug','installedVersion','observedVersion','entityId','error','installSubmitted','installRefusedVerified','nativeInstalledVersion','errorCode')
        return {k:state[k] for k in keys if k in state}

    def require_exclusive(self):
        reset=self.data/'installation-reset.json'
        if reset.exists() and json.loads(reset.read_text()).get('state') in ('backing_up','removing','partial','backup_uncertain'):
            raise RuntimeError('Terminez la remise à zéro avant de mettre à jour cette box.')

    def preflight(self,target=None,*,observe=False):
        info=self.supervisor('/addons/self/info')
        repo=info.get('repository');slug=info.get('slug')
        if repo not in REPOSITORIES or slug!=repo+'_agent_123_domotique':raise RuntimeError('Cette box ne provient pas du dépôt La Box autorisé.')
        # Supervisor's native repository ID is derived from the installed Git
        # URL. It is matched against known, operator-bootstrapped La Box sources;
        # this is no claim of a cryptographic URL or image/source attestation.
        rows=self.registry()
        if not isinstance(rows,list):raise RuntimeError('Le registre de mise à jour est indisponible.')
        matches=[r for r in rows if r.get('platform')=='hassio' and r.get('unique_id')==slug+'_version_latest'
                 and not r.get('disabled_by') and isinstance(r.get('entity_id'),str)
                 and re.fullmatch(r'update\.[a-z0-9_]+',r['entity_id'])]
        if len(matches)!=1:raise RuntimeError('La mise à jour native de cet agent ne peut pas être identifiée.')
        entity=matches[0]['entity_id'];state=self.call('/states/'+entity);attrs=state.get('attributes',{})
        current,latest=info.get('version'),info.get('version_latest')
        version(current)
        if attrs.get('installed_version')!=current:raise RuntimeError('La version native de cette box est encore en cours de vérification.')
        if not observe:
            if current!=self.runtime_version:raise RuntimeError('La version de l’agent et celle de Home Assistant ne concordent pas.')
            if info.get('auto_update') is not False or attrs.get('auto_update') is not False:
                raise RuntimeError('Désactivez la mise à jour automatique avant de choisir une version depuis le portail.')
            if state.get('state') not in ('on','off') or attrs.get('in_progress') is True or not isinstance(attrs.get('supported_features'),int) or not attrs['supported_features']&1:
                raise RuntimeError('La mise à jour native de cette box n’est pas disponible.')
            if target is not None:
                version(target,stable=True)
                if target!=latest or attrs.get('latest_version')!=target:raise RuntimeError('Le catalogue a changé. Une nouvelle validation de la version est nécessaire.')
                if version(target)<=version(current):raise RuntimeError('La mise à jour doit être plus récente que la version installée.')
        return {'installedVersion':current,'latestVersion':latest,'entityId':entity,'slug':slug,'repository':repo}

    def reconcile_status(self,state):
        if not state:return state
        if state.get('state') == 'refreshing_catalog' and str(self.path) not in _WORKERS:
            state['state']='failed';state['error']='La préparation a été interrompue. Aucune installation n’a été lancée.';self.save(state)
        if state.get('state') == 'backing_up' and str(self.path) not in _WORKERS:
            state['state']='backup_uncertain';state['error']='La sauvegarde doit être vérifiée avant toute installation.';self.save(state)
        if state.get('installSubmitted') and state.get('state') not in ('completed','failed','attention_required'):
            state['observedVersion']=self.runtime_version
            try:actual=self.preflight(observe=True)
            except Exception:return state
            if actual['installedVersion']==state['targetVersion'] and self.runtime_version==state['targetVersion']:
                state['state']='completed';state['nativeInstalledVersion']=actual['installedVersion'];state.pop('error',None)
            elif self.runtime_version!=state['installedVersion'] and self.runtime_version!=state['targetVersion']:
                state['state']='attention_required';state['error']='Une autre version a été observée. Aucun nouvel essai automatique n’est effectué.'
            else:state['state']='awaiting_restart'
            with _MUTEX:
                current=self.load()
                if (current.get('operationId')!=state.get('operationId') or current.get('ownerScope')!=state.get('ownerScope')
                        or current.get('state')=='completed'):
                    return current
                self.save(state)
        return state

    def observe_heartbeat(self):
        """Nonblocking post-restart observation, never installer resumption."""
        with _MUTEX:
            state=self.load()
            if state.get('state')=='refreshing_catalog' and str(self.path) not in _WORKERS:
                state['state']='failed';state['error']='La préparation a été interrompue. Aucune installation n’a été lancée.';self.save(state)
            if state.get('state')=='backing_up' and str(self.path) not in _WORKERS:
                state['state']='backup_uncertain';state['error']='La sauvegarde doit être vérifiée avant toute installation.';self.save(state)
            if (not state.get('installSubmitted') or state.get('state') in ('completed','failed','attention_required')
                    or self.runtime_version==state.get('installedVersion') or str(self.path) in _OBSERVERS):
                return heartbeat_status(self.runtime_version,self.data)
            identifier=state.get('operationId')
            def observe():
                try:
                    with _MUTEX:
                        latest=self.load()
                        if latest.get('operationId')!=identifier:return
                    # Callbacks used here have short metadata-only timeouts.
                    updated=self.reconcile_status(latest)
                except Exception:
                    pass
                finally:
                    with _MUTEX:_OBSERVERS.pop(str(self.path),None)
            worker=threading.Thread(target=observe,daemon=True,name='installation-update-observer')
            _OBSERVERS[str(self.path)]=worker;worker.start()
            return heartbeat_status(self.runtime_version,self.data)

    def prepare_catalog(self,operation_id):
        """Refresh metadata only. Never backs up or installs without execute."""
        phase='preflight'
        try:
            fd=os.open(self.data/'installation-maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                state=self.load()
                if state.get('operationId')!=operation_id or state.get('state')!='refreshing_catalog':return
                self.require_exclusive();self.require_admin()
                before=self.preflight()
                if any(before[k]!=state[k] for k in ('entityId','slug','repository','installedVersion')):
                    raise RuntimeError('La cible de mise à jour a changé.')
                phase='refresh'
                self.refresh_catalog(state['entityId'])
                phase='target'
                for attempt in range(46):
                    self.require_exclusive();self.require_admin()
                    try:
                        actual=self.preflight(state['targetVersion'])
                        break
                    except RuntimeError:
                        if attempt==45:raise
                        self.sleep(2)
                if any(actual[k]!=state[k] for k in ('entityId','slug','repository','installedVersion')):
                    raise RuntimeError('La cible de mise à jour a changé.')
                with _MUTEX:
                    current=self.load()
                    if current.get('operationId')!=operation_id or current.get('state')!='refreshing_catalog':return
                    state.update(actual,state='prepared',expiresAt=int(self.clock())+TTL)
                    state['previewHash']=digest({k:state[k] for k in ('operationId','consentId','targetVersion','releaseCommit','ownerScope','expiresAt','entityId','slug','repository','installedVersion')})
                    self.save(state)
        except Exception:
            with _MUTEX:
                state=self.load()
                if state.get('operationId')==operation_id and state.get('state')=='refreshing_catalog':
                    state.update(state='failed',errorCode='catalog_'+phase+'_failed',error={'preflight':'Les droits ou l’identité de cette box n’ont pas pu être vérifiés. Aucune installation n’a été lancée.','refresh':'Home Assistant n’a pas pu actualiser la mise à jour de cette box. Aucune installation n’a été lancée.','target':'La version proposée n’est pas disponible ou le catalogue a changé. Aucune installation n’a été lancée.'}[phase])
                    self.save(state)
        finally:
            with _MUTEX:_WORKERS.pop(str(self.path),None)

    def work(self,operation_id):
        try:
            fd=os.open(self.data/'installation-maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                state=self.load()
                if state.get('operationId')!=operation_id or state.get('installSubmitted'):return
                self.require_exclusive();self.require_admin()
                current=self.preflight(state['targetVersion'])
                if any(current[k]!=state[k] for k in ('entityId','slug','repository','installedVersion')):raise RuntimeError('La cible de mise à jour a changé.')
                self.backup(state)
                self.require_exclusive();self.require_admin()
                current=self.preflight(state['targetVersion'])
                if any(current[k]!=state[k] for k in ('entityId','slug','repository','installedVersion')):raise RuntimeError('La cible de mise à jour a changé.')
                # Journal before the call: a stopped/restarted agent never
                # repeats update.install, even if the response is lost.
                state.update(state='installing',installSubmitted=True,submittedAt=self.clock());self.save(state)
                try:
                    self.call('/services/update/install',method='POST',payload={'entity_id':state['entityId'],'backup':False},timeout=15)
                except urllib.error.HTTPError as error:
                    if error.code in (401,403,404,405):
                        state.update(installRefusedVerified=True,refusalHttpStatus=error.code);self.save(state)
                        raise
                except (TimeoutError,urllib.error.URLError,ConnectionError):pass
                state['state']='awaiting_restart';self.save(state)
        except Exception:
            state=self.load()
            if state.get('operationId')!=operation_id:return
            state['state']=('awaiting_restart' if state.get('installSubmitted') and state.get('installRefusedVerified') is not True else 'failed' if not state.get('backupSubmitted') or state.get('installSubmitted') or state.get('backupVerified') else 'backup_uncertain')
            state['error']='La mise à jour n’est pas confirmée. Aucun nouvel essai d’installation automatique n’est effectué.'
            self.save(state)
        finally:
            with _MUTEX:_WORKERS.pop(str(self.path),None)

    def command(self,payload):
        owner=payload.get('ownerScope');operation=payload.get('operation')
        if not isinstance(owner,str) or not re.fullmatch('[a-f0-9]{64}',owner):raise ValueError('Le propriétaire doit être vérifié.')
        with _MUTEX:
            state=self.load()
            if state and state.get('ownerScope')!=owner:
                if operation=='status':return {'state':'idle','observedVersion':self.runtime_version}
                if (operation=='prepare' and state.get('state') not in ACTIVE
                        and (not state.get('installSubmitted') or state.get('state')=='completed' or state.get('installRefusedVerified') is True)
                        and str(self.path) not in _WORKERS and _valid_uuid(state.get('operationId'))):
                    archive=self.data/('installation-update-'+state['operationId']+'.json')
                    fd=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w') as file:json.dump(state,file);file.flush();os.fsync(file.fileno())
                    state={};self.save(state)
                else:raise RuntimeError('Cette mise à jour appartient à une autre autorisation propriétaire.')
            if operation=='status':
                if payload.get('operationId') and payload['operationId']!=state.get('operationId'):raise RuntimeError('Cette opération de mise à jour est introuvable.')
                if not state:
                    # Qualification of an older box after operator bootstrap:
                    # only native metadata reads, no consent/journal or backup.
                    result={'state':'idle','observedVersion':self.runtime_version,'nativeReady':False}
                    try:
                        self.require_exclusive();self.require_admin()
                        actual=self.preflight()
                        backups=self.supervisor('/backups')
                        if not isinstance(backups,dict) or not isinstance(backups.get('backups'),list):raise RuntimeError()
                        result.update(nativeReady=True,installedVersion=actual['installedVersion'],latestVersion=actual['latestVersion'])
                    except Exception:
                        result['readinessError']='Les permissions ou la mise à jour native de cette box doivent être vérifiées.'
                    return result
                return self.public(self.reconcile_status(state))
            identifier=payload.get('operationId');consent=payload.get('consentId');target=payload.get('targetVersion');commit=payload.get('releaseCommit')
            if not _valid_uuid(identifier) or not _valid_uuid(consent) or not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('L’autorisation de mise à jour est invalide.')
            version(target,stable=True)
            if operation not in ('prepare','execute'):raise ValueError('Opération de mise à jour inconnue.')
            self.require_exclusive();self.require_admin()
            if operation=='execute' and (payload.get('confirmed') is not True or payload.get('previewHash')!=state.get('previewHash')):
                raise ValueError('Confirmez exactement la version préparée.')
            if state.get('operationId')==identifier:
                if any(state.get(k)!=payload.get(k) for k in ('consentId','targetVersion','releaseCommit')):raise RuntimeError('Cette opération est liée à une autre version ou à un autre consentement.')
                state=self.reconcile_status(state)
                if state.get('installSubmitted') or str(self.path) in _WORKERS:return self.public(state)
            elif state and (str(self.path) in _WORKERS or state.get('state') in ACTIVE or
                    (state.get('installSubmitted') and state.get('state')!='completed'
                     and state.get('installRefusedVerified') is not True)):
                raise RuntimeError('La mise à jour précédente doit d’abord être vérifiée. Aucun nouvel envoi n’est autorisé.')
            if operation=='prepare':
                if state.get('operationId')==identifier:return self.public(state)
                actual=self.preflight() if self.refresh_catalog else self.preflight(target)
                if version(target)<=version(actual['installedVersion']):raise RuntimeError('La mise à jour doit être plus récente que la version installée.')
                state={**actual,'operationId':identifier,'consentId':consent,'targetVersion':target,'releaseCommit':commit,
                       'ownerScope':owner,'expiresAt':int(self.clock())+TTL,'state':'refreshing_catalog' if self.refresh_catalog else 'prepared','backupVerified':False,'installSubmitted':False}
                if self.refresh_catalog:
                    self.save(state)
                    worker=threading.Thread(target=self.prepare_catalog,args=(identifier,),daemon=True,name='installation-update')
                    _WORKERS[str(self.path)]=worker
                    try:worker.start()
                    except Exception:
                        _WORKERS.pop(str(self.path),None);state.update(state='failed',error='La préparation n’a pas démarré. Aucune installation n’a été lancée.');self.save(state);raise
                else:
                    state['previewHash']=digest({k:state[k] for k in ('operationId','consentId','targetVersion','releaseCommit','ownerScope','expiresAt','entityId','slug','repository','installedVersion')})
                    self.save(state)
                return self.public(state)
            if state.get('operationId')!=identifier:raise RuntimeError('Préparez cette mise à jour avant de la lancer.')
            if payload.get('confirmed') is not True or payload.get('previewHash')!=state.get('previewHash'):raise ValueError('Confirmez exactement la version préparée.')
            if self.clock()>state['expiresAt']:raise RuntimeError('Cette confirmation a expiré. Préparez une nouvelle opération.')
            if state.get('state') not in ('prepared','backup_uncertain'):return self.public(state)
            actual=self.preflight(target)
            if any(actual[k]!=state[k] for k in ('entityId','slug','repository','installedVersion')):raise RuntimeError('La cible de mise à jour a changé.')
            state['state']='backing_up';self.save(state)
            worker=threading.Thread(target=self.work,args=(identifier,),daemon=True,name='installation-update');_WORKERS[str(self.path)]=worker;worker.start()
            return self.public(state)


def heartbeat_status(runtime_version,data=Path('/data')):
    """Authenticated agent heartbeat evidence, never self-asserted install success."""
    path=Path(data)/'installation-update.json'
    if not path.exists():return None
    try:state=json.loads(path.read_text())
    except Exception:return None
    required=('operationId','ownerScope','consentId','targetVersion','releaseCommit','state','backupVerified','installedVersion')
    if any(key not in state for key in required):return None
    evidence={key:state[key] for key in required}
    for key in ('backupSlug','previewHash','expiresAt','error','installSubmitted','submittedAt','installRefusedVerified','nativeInstalledVersion','errorCode'):
        if key in state:evidence[key]=state[key]
    evidence['observedVersion']=runtime_version
    return evidence
