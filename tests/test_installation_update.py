import json
from pathlib import Path
import tempfile
import unittest
import uuid
import urllib.error
from unittest.mock import patch
from installation_update import Update,REPOSITORIES,heartbeat_status,busy

OWNER='1'*64
TARGET='0.6.1'
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name);self.clock=1000
  self.repo=next(k for k,v in REPOSITORIES.items() if '#codex/' in v);self.slug=self.repo+'_agent_123_domotique';self.running='0.6.1-dev24';self.latest=TARGET;self.installed=self.running;self.auto=False;self.failbackup=False;self.lost=False;self.writes=[];self.backups=[];self.installs=[]
  self.operation=str(uuid.uuid4());self.consent=str(uuid.uuid4());self.base={'operationId':self.operation,'consentId':self.consent,'ownerScope':OWNER,'targetVersion':TARGET,'releaseCommit':'a'*40}
  self.rows=[{'platform':'hassio','unique_id':self.slug+'_version_latest','entity_id':'update.agent_labo'}]
  self.engine=self.new_engine()
 def new_engine(self):
  return Update(self.call,self.supervisor,lambda slug:{'verified':True,'addons':[self.slug]},registry=lambda:self.rows,runtime_version=self.running,authorize=lambda:{'is_admin':True},data=self.data,clock=lambda:self.clock,sleep=lambda _:None)
 def call(self,path,method='GET',payload=None,**kw):
  if path=='/states/update.agent_labo':return {'state':'on','attributes':{'installed_version':self.installed,'latest_version':self.latest,'auto_update':self.auto,'in_progress':False,'supported_features':1}}
  if path=='/services/update/install':
   self.installs.append(payload);self.writes.append(path)
   if self.lost:raise TimeoutError('restart lost response')
   return []
  raise AssertionError(path)
 def supervisor(self,path,method='GET',payload=None,**kw):
  if path=='/addons/self/info':return {'slug':self.slug,'repository':self.repo,'version':self.installed,'version_latest':self.latest,'auto_update':self.auto}
  if path=='/backups/new/full':
   if self.failbackup:raise RuntimeError('no backup')
   self.backups.append({'slug':'backup1','name':payload['name']});return {'slug':'backup1'}
  if path=='/backups':return {'backups':self.backups}
  if path=='/backups/backup1/info':return {**self.backups[0],'type':'full','homeassistant':'2026.10.1','homeassistant_exclude_database':False,'size':12,'addons':[{'slug':self.slug}]}
  raise AssertionError(path)
 def prepare(self):return self.engine.command(self.base|{'operation':'prepare'})
 def execute(self,preview):
  with patch('installation_update.threading.Thread'):
   self.engine.command(self.base|{'operation':'execute','confirmed':True,'previewHash':preview['previewHash']})
  import installation_update
  installation_update._WORKERS.pop(str(self.engine.path),None)
  self.engine.work(self.operation)
  return self.engine.load()
 def test_idle_status_qualifies_native_access_without_journal_or_backup(self):
  status=self.engine.command({'operation':'status','ownerScope':OWNER})
  self.assertEqual(status['state'],'idle');self.assertTrue(status['nativeReady']);self.assertEqual(status['latestVersion'],TARGET)
  self.assertFalse(self.engine.path.exists());self.assertEqual(self.backups,[]);self.assertEqual(self.installs,[])
 def test_idle_readiness_failure_is_bounded_and_never_mutates(self):
  self.auto=True;status=self.engine.command({'operation':'status','ownerScope':OWNER})
  self.assertFalse(status['nativeReady']);self.assertIn('readinessError',status);self.assertFalse(self.engine.path.exists());self.assertEqual(self.writes,[])
 def test_backup_failure_never_submits_install(self):
  preview=self.prepare();self.failbackup=True;state=self.execute(preview)
  self.assertFalse(state['backupVerified']);self.assertEqual(self.installs,[]);self.assertEqual(state['state'],'backup_uncertain')
 def test_catalog_target_changed_before_execute_never_backups_or_installs(self):
  preview=self.prepare();self.latest='0.6.2'
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.backups,[]);self.assertEqual(self.installs,[])
 def test_catalog_change_during_backup_never_installs(self):
  preview=self.prepare();verify=self.engine.verify_archive
  def change(slug):self.latest='0.6.2';return verify(slug)
  self.engine.verify_archive=change;state=self.execute(preview)
  self.assertTrue(state['backupVerified']);self.assertEqual(self.installs,[]);self.assertNotEqual(state['state'],'completed')
 def test_lost_install_ack_never_replays_on_retry_or_restart(self):
  preview=self.prepare();self.lost=True;state=self.execute(preview);self.assertEqual(state['state'],'awaiting_restart');self.assertTrue(state['installSubmitted']);self.assertEqual(len(self.installs),1)
  self.engine=self.new_engine();self.engine.command(self.base|{'operation':'execute','confirmed':True,'previewHash':preview['previewHash']})
  self.assertEqual(len(self.installs),1);self.assertEqual(len(self.backups),1)
 def test_success_requires_observed_runtime_and_native_installed_version(self):
  preview=self.prepare();state=self.execute(preview);self.assertNotEqual(state['state'],'completed')
  self.installed=TARGET
  self.assertNotEqual(self.engine.command({'operation':'status','ownerScope':OWNER})['state'],'completed')
  self.running=TARGET;self.engine=self.new_engine();status=self.engine.command({'operation':'status','ownerScope':OWNER})
  self.assertEqual(status['state'],'completed');self.assertEqual(status['observedVersion'],TARGET)
 def test_other_runtime_version_is_attention_required_not_success(self):
  preview=self.prepare();self.execute(preview);self.running='0.6.2';self.installed=self.running;self.engine=self.new_engine()
  self.assertEqual(self.engine.command({'operation':'status','ownerScope':OWNER})['state'],'attention_required');self.assertEqual(len(self.installs),1)
 def test_auto_update_downgrade_development_or_wrong_source_refused(self):
  self.auto=True
  with self.assertRaises(RuntimeError):self.prepare()
  self.auto=False
  for target in ('0.6.1-dev25','0.6.0'):
   with self.assertRaises((RuntimeError,ValueError)):self.engine.command(self.base|{'operation':'prepare','targetVersion':target})
  self.repo='unknown'
  with self.assertRaises(RuntimeError):self.prepare()
  self.assertEqual(self.installs,[])
 def test_reset_active_blocks_update_but_readonly_preview_does_not(self):
  reset=self.data/'installation-reset.json';reset.write_text(json.dumps({'state':'backing_up'}))
  with self.assertRaises(RuntimeError):self.prepare()
  reset.write_text(json.dumps({'state':'prepared'}));self.assertEqual(self.prepare()['state'],'prepared')
 def test_wrong_owner_or_operation_tuple_is_refused(self):
  preview=self.prepare()
  self.assertEqual(self.engine.command({'operation':'status','ownerScope':'2'*64})['state'],'idle')
  with self.assertRaises(RuntimeError):self.engine.command(self.base|{'operation':'execute','confirmed':True,'previewHash':preview['previewHash'],'releaseCommit':'b'*40})
  self.assertEqual(self.installs,[])
 def test_expired_confirmation_and_wrong_ha_entity_never_install(self):
  preview=self.prepare();self.clock=3000
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.installs,[]);self.assertEqual(self.backups,[])
  self.clock=1000;self.rows[0]['unique_id']='other_addon_version_latest'
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.installs,[])
 def test_same_operation_never_rebinds_target_and_preview(self):
  preview=self.prepare()
  with self.assertRaises(ValueError):self.engine.command(self.base|{'operation':'execute','confirmed':True,'previewHash':'b'*64})
  self.assertEqual(self.installs,[])
 def test_failed_or_attention_after_submission_blocks_any_new_operation(self):
  preview=self.prepare();self.execute(preview)
  for phase in ('failed','attention_required'):
   state=self.engine.load();state['state']=phase;self.engine.save(state)
   with self.subTest(state=phase),self.assertRaises(RuntimeError):
    self.engine.command(self.base|{'operation':'prepare','operationId':str(uuid.uuid4()),'consentId':str(uuid.uuid4())})
  self.assertEqual(len(self.installs),1)
 def test_permission_refusal_is_distinct_and_new_explicit_operation_allowed(self):
  preview=self.prepare();original=self.engine.call
  def refuse(path,**kwargs):
   if path=='/services/update/install':raise urllib.error.HTTPError('url',403,'forbidden',{},None)
   return original(path,**kwargs)
  self.engine.call=refuse;state=self.execute(preview)
  self.assertEqual(state['state'],'failed');self.assertTrue(state['installRefusedVerified'])
  self.engine.call=original
  new=self.engine.command(self.base|{'operation':'prepare','operationId':str(uuid.uuid4()),'consentId':str(uuid.uuid4())})
  self.assertEqual(new['state'],'prepared');self.assertFalse(new['installSubmitted'])
 def test_heartbeat_observation_reconciles_real_versions_and_releases_busy(self):
  import installation_update
  preview=self.prepare();self.execute(preview);self.assertTrue(busy(self.data))
  self.running=TARGET;self.installed=TARGET;self.engine=self.new_engine()
  self.engine.observe_heartbeat()
  worker=installation_update._OBSERVERS.get(str(self.engine.path))
  if worker:worker.join(timeout=2)
  evidence=heartbeat_status(TARGET,self.data)
  self.assertEqual(evidence['state'],'completed');self.assertEqual(evidence['installedVersion'],'0.6.1-dev24')
  self.assertEqual(evidence['nativeInstalledVersion'],TARGET);self.assertEqual(evidence['observedVersion'],TARGET);self.assertFalse(busy(self.data));self.assertEqual(len(self.installs),1)
 def test_heartbeat_native_version_lag_does_not_claim_complete_or_retry(self):
  import installation_update
  preview=self.prepare();self.execute(preview);self.running=TARGET;self.engine=self.new_engine()
  self.engine.observe_heartbeat();worker=installation_update._OBSERVERS.get(str(self.engine.path))
  if worker:worker.join(timeout=2)
  self.assertNotEqual(self.engine.load()['state'],'completed');self.assertTrue(busy(self.data));self.assertEqual(len(self.installs),1)
 def test_authenticated_heartbeat_tuple_does_not_claim_completion(self):
  preview=self.prepare();self.execute(preview);evidence=heartbeat_status(TARGET,self.data)
  self.assertEqual(evidence['ownerScope'],OWNER);self.assertEqual(evidence['consentId'],self.consent);self.assertEqual(evidence['observedVersion'],TARGET);self.assertEqual(evidence['state'],'awaiting_restart');self.assertTrue(evidence['installSubmitted'])

if __name__=='__main__':unittest.main()
