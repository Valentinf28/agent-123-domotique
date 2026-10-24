import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from installation_update import Update, REPOSITORIES

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name);self.now=10000;self.owner='1'*64;self.current='0.6.39';self.repo=next(iter(REPOSITORIES));self.slug=self.repo+'_agent_123_domotique';self.admin=True;self.progress=False;self.verified=True
  self.old={'operationId':str(uuid.uuid4()),'ownerScope':'2'*64,'targetVersion':'0.6.32','installedVersion':'0.6.31','observedVersion':'0.6.33','state':'attention_required','installSubmitted':True,'backupVerified':True}
  self.backup={'slug':'fresh','type':'full','date':datetime.fromtimestamp(self.now,timezone.utc).isoformat(),'homeassistant':'2026.10','homeassistant_exclude_database':False,'addons':[{'slug':self.slug}]}
  self.engine=Update(self.call,self.supervisor,lambda _: {'verified':self.verified,'addons':[self.slug]},registry=lambda:[{'platform':'hassio','unique_id':self.slug+'_version_latest','entity_id':'update.agent'}],runtime_version=self.current,authorize=lambda:{'is_admin':self.admin},data=self.data,clock=lambda:self.now)
  self.engine.save(self.old);self.request={'ownerScope':self.owner,'operationId':str(uuid.uuid4())}
 def call(self,path,**kwargs):
  self.assertEqual(path,'/states/update.agent');self.assertEqual(kwargs,{})
  return {'state':'on','attributes':{'installed_version':self.current,'in_progress':self.progress,'auto_update':False}}
 def supervisor(self,path,**kwargs):
  self.assertEqual(kwargs,{})
  if path=='/addons/self/info':return {'slug':self.slug,'repository':self.repo,'version':self.current}
  if path=='/backups/fresh/info':return copy.deepcopy(self.backup)
  raise AssertionError(path)
 def preview(self):return self.engine.recover_command(self.request|{'operation':'recovery_preview'})
 def commit(self,preview,**extra):return self.engine.recover_command(self.request|{'operation':'recovery_commit','confirmed':True,'backupSlug':'fresh','previewHash':preview['previewHash']}|extra)
 def test_completed_recovery_is_idempotent_for_same_confirmation_only(self):
  preview=self.preview();first=self.commit(preview);self.assertEqual(self.commit(preview),first)
  with self.assertRaises(RuntimeError):self.commit(preview,backupSlug='other')
 def test_preview_does_not_change_old_journal_or_install(self):
  self.assertTrue(self.preview()['requiresBackup']);self.assertEqual(self.engine.load(),self.old)
 def test_commit_archives_complete_original_and_keeps_recovery_marker(self):
  result=self.commit(self.preview());self.assertTrue(result['oldJournalArchived']);self.assertFalse(result['willInstall']);self.assertEqual(self.engine.load()['state'],'recovered');self.assertFalse(self.engine.load()['installSubmitted']);self.assertEqual(self.engine.command({'operation':'status','ownerScope':self.owner})['state'],'idle')
  p=next(self.data.glob('installation-update-retired-*.json'));self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(p.read_text())['original'],self.old)
 def test_confirmation_hash_owner_and_expiry_are_strict(self):
  for extra in [{'confirmed':False},{'previewHash':'bad'},{'ownerScope':'3'*64}]:
   preview=self.preview()
   with self.assertRaises(RuntimeError):self.commit(preview,**extra)
   self.assertEqual(self.engine.load(),self.old)
  preview=self.preview();self.now+=901
  with self.assertRaises(RuntimeError):self.commit(preview)
 def test_active_or_uncertain_journal_not_recoverable(self):
  for state in ['backing_up','backup_uncertain','installing','awaiting_restart','prepared','failed']:
   self.engine.save(self.old|{'state':state})
   with self.assertRaises(RuntimeError):self.preview()
 def test_same_or_older_runtime_not_a_superseded_operation(self):
  self.engine.save(self.old|{'targetVersion':'0.6.39'})
  with self.assertRaises(RuntimeError):self.preview()
 def test_native_update_in_progress_or_missing_admin_refused(self):
  self.progress=True
  with self.assertRaises(RuntimeError):self.preview()
  self.progress=False;self.admin=False
  with self.assertRaises(RuntimeError):self.preview()
 def test_stale_incomplete_and_unverified_backups_cannot_retire(self):
  for patch in [{'date':datetime.fromtimestamp(1,timezone.utc).isoformat()},{'addons':[]},{'homeassistant_exclude_database':True},{'type':'partial'}]:
   self.backup.update(patch)
   with self.assertRaises(RuntimeError):self.commit(self.preview())
   self.assertEqual(self.engine.load(),self.old)
   self.setUpBackup()
  self.verified=False
  with self.assertRaises(RuntimeError):self.commit(self.preview())
 def setUpBackup(self):self.backup={'slug':'fresh','type':'full','date':datetime.fromtimestamp(self.now,timezone.utc).isoformat(),'homeassistant':'2026.10','homeassistant_exclude_database':False,'addons':[{'slug':self.slug}]}
 def test_concurrent_change_keeps_journal_and_refuses_commit(self):
  preview=self.preview();self.engine.save(self.old|{'error':'changed'})
  with self.assertRaises(RuntimeError):self.commit(preview)
  self.assertEqual(self.engine.load()['error'],'changed');self.assertFalse(list(self.data.glob('installation-update-retired-*.json')))

if __name__=='__main__':unittest.main()
