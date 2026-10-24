"""Pinned, owner-consented Core maintenance. No OS updates or automatic restore.

The journal is durable before every external mutation. Lost responses are only
observed; installation and backup creation are never replayed after restart.
"""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from installation_reset import Reset, _MUTEX, _valid_uuid, digest

ACTIVE={'preparing','backing_up','backup_uncertain','installing','verifying','attention_required','restoring'}
_WORKERS={}
# This bridge publishes a cached configuration document after maintenance. It is
# transient HA REST state, not equipment availability. Legacy journals may include it.
TRANSIENT_ENTITIES=frozenset({'sensor.home_local_configuration'})
VERSION=re.compile(r'^202[6-9]\.(?:[1-9]|1[0-2])\.(?:0|[1-9][0-9]{0,2})$')

def version(value):
    if not isinstance(value,str) or not VERSION.fullmatch(value):raise ValueError('Choisissez une version stable officielle de Home Assistant.')
    return tuple(map(int,value.split('.')))

def busy(data=Path('/data')):
    try:
        p=Path(data)/'core-update.json'
        return p.exists() and json.loads(p.read_text()).get('state') in ACTIVE
    except Exception:return True

class CoreUpdate(Reset):
    backup_name='La Box avant mise à jour du système '
    def __init__(self,*args,registry,free_bytes=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.path=self.data/'core-update.json';self.registry=registry
        self.free_bytes=free_bytes or (lambda:shutil.disk_usage('/homeassistant_config').free)

    def public(self,state):
        keys=('arch','operationId','ownerScope','consentId','releaseId','targetVersion','installedVersion','state','previewHash','expiresAt','inventoryHash','inventory','backupSlug','backupVerified','installSubmitted','observedVersion','checks','error','completedAt','backupReusable','backupLimit','restoreSubmitted','restorePreviewHash','restoreExpiresAt')
        return {k:state[k] for k in keys if k in state} if state else {'state':'idle'}

    def snapshot(self):
        rows=self.call('/config/config_entries/entry');states=self.call('/states')
        if not isinstance(rows,list) or not isinstance(states,list):raise RuntimeError('Le bilan des équipements est indisponible.')
        entries=[{'id':e['entry_id'],'domain':e['domain'],'state':e['state']} for e in rows if not e.get('disabled_by')]
        domains=sorted({e['domain'] for e in entries})
        custom=[]
        for domain in domains:
            p=Path('/homeassistant_config/custom_components')/domain/'manifest.json'
            if p.is_file():
                m=json.loads(p.read_text());custom.append({'domain':domain,'version':str(m.get('version','unknown'))[:80],'manifestHash':digest(m)})
        important=('climate.','switch.','sensor.','automation.','number.','select.','water_heater.')
        available=sorted(s['entity_id'] for s in states if s.get('entity_id','').startswith(important) and s.get('state') not in ('unavailable','unknown') and s['entity_id'] not in TRANSIENT_ENTITIES)
        automations={s['entity_id']:s['state'] for s in states if s.get('entity_id','').startswith('automation.') and s.get('state') in ('on','off')}
        return {'entries':sorted(entries,key=lambda e:e['id']),'domains':domains,'custom':custom,'available':available,'automations':automations,'existingFailures':[e for e in entries if e['state']!='loaded']}

    def inspect(self,target=None):
        self.require_admin();core=self.supervisor('/core/info');sup=self.supervisor('/supervisor/info');config=self.call('/config')
        current=core.get('version');latest=core.get('version_latest');version(current);version(latest)
        if config.get('version')!=current or config.get('state')!='RUNNING' or config.get('safe_mode') is True:raise RuntimeError('Le système doit être démarré normalement avant cette opération.')
        if sup.get('healthy') is not True or sup.get('supported') is not True or sup.get('channel')!='stable':raise RuntimeError('La santé du système ou son canal stable doit être vérifié.')
        if not str(core.get('image','')).startswith('ghcr.io/home-assistant/') or core.get('arch') not in ('aarch64','amd64'):raise RuntimeError('Cette installation nécessite une vérification technique.')
        if self.free_bytes()<5*1024**3:raise RuntimeError('Au moins 5 Go libres sont nécessaires avant la mise à jour.')
        if target and not version(current)<version(target)<=version(latest):raise RuntimeError('La version approuvée ne correspond pas aux versions disponibles.')
        inventory=self.snapshot()
        return {'installedVersion':current,'latestVersion':latest,'arch':core['arch'],'inventory':inventory,'inventoryHash':digest(inventory)}

    def exclusive(self):
        if self.backup_guard:self.backup_guard()
        from installation_update import busy as agent_busy
        if agent_busy(self.data):raise RuntimeError('Attendez la fin de la mise à jour de l’agent.')
        for name,states in [('installation-reset.json',{'backing_up','removing','partial','backup_uncertain'}),('factory-stage.json',{'preparing','prepared','committing'})]:
            p=self.data/name
            if p.exists() and json.loads(p.read_text()).get('state') in states:raise RuntimeError('Une autre intervention est en cours.')

    def reuse_backup(self,slug,state):
        # Only reuse the just-verified full backup from this owner's preceding
        # agent update. Arbitrary old archives never bypass capacity or freshness.
        p=self.data/'installation-update.json';prior=json.loads(p.read_text()) if p.exists() else {}
        if prior.get('state')!='completed' or prior.get('ownerScope')!=state['ownerScope'] or prior.get('backupSlug')!=slug or prior.get('backupVerified') is not True:raise RuntimeError('Cette sauvegarde doit être créée et vérifiée pour cette installation.')
        info=self.supervisor('/backups/'+slug+'/info')
        stamp=datetime.fromisoformat(info.get('date','').replace('Z','+00:00')).timestamp()
        if not 0<=self.clock()-stamp<=6*3600 or info.get('type')!='full' or info.get('homeassistant')!=state['installedVersion'] or info.get('homeassistant_exclude_database') is not False:raise RuntimeError('Cette sauvegarde est trop ancienne ou incomplète.')
        proof=self.verify_archive(slug)
        if proof.get('verified') is not True or proof.get('sha256')!=prior.get('backupArchive',{}).get('sha256'):raise RuntimeError('L’archive de sauvegarde a changé.')
        state.update(backupSlug=slug,backupVerified=True,backupArchive=proof);self.save(state)

    def prepare(self,identifier):
        try:
            with self.lock():
                s=self.load();self.exclusive();view=self.inspect(s['targetVersion'])
                self.supervisor('/core/check',method='POST',payload={},timeout=90)
                s.update(view,state='prepared',expiresAt=int(self.clock())+900)
                s['previewHash']=digest({k:s[k] for k in ('operationId','ownerScope','consentId','releaseId','targetVersion','inventoryHash','expiresAt','backupSlug','backupLimit')})
                self.save(s)
        except Exception:
            s=self.load()
            if s.get('operationId')==identifier:s.update(state='failed',error='La préparation du système a échoué. Aucune mise à jour n’a été lancée.');self.save(s)
        finally:_WORKERS.pop(str(self.path),None)

    def lock(self):
        from contextlib import contextmanager
        @contextmanager
        def acquire():
            fd=os.open(self.data/'installation-maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        return acquire()

    def execute(self,identifier):
        try:
            with self.lock():
                s=self.load();self.exclusive();current=self.inspect(s['targetVersion'])
                if current['inventoryHash']!=s['inventoryHash']:raise RuntimeError('La configuration a changé.')
                if s['backupSlug']:self.reuse_backup(s['backupSlug'],s)
                else:
                    listing=self.supervisor('/backups').get('backups')
                    if not isinstance(listing,list) or len(listing)>=s['backupLimit']:raise RuntimeError('La limite de sauvegardes est atteinte.')
                    self.backup(s)
                self.exclusive();current=self.inspect(s['targetVersion'])
                if current['inventoryHash']!=s['inventoryHash']:raise RuntimeError('La configuration a changé.')
                self.supervisor('/core/check',method='POST',payload={},timeout=90)
                s.update(state='installing',installSubmitted=True,submittedAt=self.clock());self.save(s)
                # Pinned version, no latest fallback, no duplicate HA backup.
                try:self.supervisor('/core/update',method='POST',payload={'version':s['targetVersion'],'backup':False,'background':True},timeout=15)
                except Exception:pass
                s['state']='verifying';self.save(s)
        except Exception:
            s=self.load()
            if s.get('operationId')!=identifier:return
            s.update(state='verifying' if s.get('installSubmitted') else 'backup_uncertain' if s.get('backupSubmitted') and not s.get('backupVerified') else 'failed',error='Le résultat doit être vérifié. Aucune installation n’est répétée automatiquement.');self.save(s)
        finally:_WORKERS.pop(str(self.path),None)

    def observe(self,s):
        if s.get('state') in ('preparing','backing_up') and str(self.path) not in _WORKERS:
            s.update(state='backup_uncertain' if s.get('backupSubmitted') else 'failed',error='L’opération a été interrompue et doit être vérifiée.');self.save(s)
        if s.get('state') not in ('verifying','attention_required'):return s
        try:
            info=self.supervisor('/core/info');config=self.call('/config');s['observedVersion']=config.get('version')
            current=self.snapshot();before=s['inventory']
            missing=sorted((set(before['available'])-TRANSIENT_ENTITIES)-set(current['available']))
            checks={'version':info.get('version')==s['targetVersion']==config.get('version'),'running':config.get('state')=='RUNNING' and config.get('safe_mode') is not True,'integrations':{(e['id'],e['domain']) for e in before['entries'] if e['state']=='loaded'}<={(e['id'],e['domain']) for e in current['entries'] if e['state']=='loaded'},'automations':all(current['automations'].get(k)==v for k,v in before['automations'].items()),'entities':not missing}
            s['checks']=checks
            if all(checks.values()):s.update(state='completed',completedAt=int(self.clock()));s.pop('error',None)
            elif self.clock()-s['submittedAt']>900:s.update(state='attention_required',error='Le contrôle après mise à jour nécessite une intervention. Le déploiement est suspendu.')
            self.save(s)
        except Exception:
            if self.clock()-s.get('submittedAt',self.clock())>900:s.update(state='attention_required',error='Le système ne répond pas normalement. Le déploiement est suspendu.');self.save(s)
        return s

    def heartbeat(self):
        s=self.load()
        if not s:return None
        if s.get('state') in ('verifying','attention_required') and s.get('installSubmitted') is True and str(self.path) not in _WORKERS:
            def inspect_once(identifier):
                try:
                    with _MUTEX:
                        current=self.load()
                        if current.get('operationId')!=identifier:return
                    self.observe(current)
                except Exception:pass
                finally:_WORKERS.pop(str(self.path),None)
            self.start(inspect_once,s['operationId'])
        return {k:v for k,v in self.public(s).items() if k not in ('inventory','previewHash','expiresAt')}

    def start(self,method,identifier):
        t=threading.Thread(target=method,args=(identifier,),daemon=True,name='core-maintenance');_WORKERS[str(self.path)]=t;t.start()

    def command(self,payload):
        operation=payload.get('operation');owner=payload.get('ownerScope')
        if not isinstance(owner,str) or not re.fullmatch('[a-f0-9]{64}',owner):raise ValueError('Propriétaire invalide.')
        fields={'inspect':set(),'status':{'operationId'},'prepare':{'operationId','consentId','releaseId','targetVersion','backupSlug','backupLimit'},'execute':{'operationId','consentId','releaseId','targetVersion','previewHash','confirmed'}}
        if operation not in fields or set(payload)!={'operation','ownerScope'}|fields[operation]:raise ValueError('Opération système invalide.')
        with _MUTEX:
            if operation=='inspect':return {'state':'inspected',**self.inspect()}
            identifier=payload.get('operationId')
            if not _valid_uuid(identifier):raise ValueError('Opération invalide.')
            s=self.load()
            if operation=='status':
                if s.get('operationId')!=identifier or s.get('ownerScope')!=owner:raise RuntimeError('Cette opération appartient à une autre association.')
                return self.public(self.observe(s))
            self.require_admin()
            if not _valid_uuid(payload.get('consentId')) or not isinstance(payload.get('releaseId'),str) or not re.fullmatch('[a-f0-9]{64}',payload['releaseId']):raise ValueError('Accord de version invalide.')
            version(payload.get('targetVersion'))
            if s.get('operationId')==identifier:
                if any(s.get(k)!=payload.get(k) for k in ('ownerScope','consentId','releaseId','targetVersion')):raise RuntimeError('L’accord a changé.')
            elif busy(self.data):raise RuntimeError('Une mise à jour doit être vérifiée avant de poursuivre.')
            if operation=='prepare':
                if s.get('operationId')==identifier:return self.public(self.observe(s))
                slug=payload['backupSlug'];limit=payload['backupLimit']
                if slug is not None and (not isinstance(slug,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',slug)) or type(limit)is not int or not 2<=limit<=6:raise ValueError('Sauvegarde invalide.')
                self.exclusive();s={**payload,'state':'preparing','backupVerified':False,'installSubmitted':False};s.pop('operation');self.save(s);self.start(self.prepare,identifier);return self.public(s)
            if s.get('operationId')!=identifier or payload['confirmed'] is not True or payload['previewHash']!=s.get('previewHash') or self.clock()>s.get('expiresAt',0):raise RuntimeError('Confirmez la préparation actualisée.')
            if s.get('installSubmitted') or str(self.path) in _WORKERS:return self.public(self.observe(s))
            if s['state']!='prepared':raise RuntimeError('La préparation n’est pas terminée.')
            s['state']='backing_up';self.save(s);self.start(self.execute,identifier);return self.public(s)
