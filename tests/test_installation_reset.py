import copy
import io
import json
import tarfile
import importlib.util
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installation_reset', Path(__file__).parents[1] / 'agent_123_domotique/installation_reset.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class InstallationResetTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.entries=[{'entry_id':'micro1','domain':'solarman','title':'Micro'}, {'entry_id':'cloud1','domain':'cloud','title':'Remote'}, {'entry_id':'weather','domain':'met','title':'Weather'}]
  self.automations={'rule1':{'id':'rule1','alias':'Pool','actions':[]}}
  self.writes=[];self.backups=[];self.now=1000;self.failbackup=False;self.lose=False
  self.engine=m.Reset(self.call,self.supervisor,lambda slug:{'verified':True,'sha256':'0'*64,'addons':['local_agent_123_domotique']},authorize=lambda:{'is_admin':True},data=Path(self.temp.name),clock=lambda:self.now,sleep=lambda _:None)
  self.operation=str(uuid.uuid4());self.owner='1'*64
 def call(self,path,method='GET',payload=None,**kw):
  if path=='/config/config_entries/entry':return copy.deepcopy(self.entries)
  if path=='/states':return [{'entity_id':'automation.'+k,'attributes':{'id':k,'friendly_name':v['alias']}} for k,v in self.automations.items()]
  if path.startswith('/config/automation/config/'):
   key=path.rsplit('/',1)[-1]
   if method=='GET':return copy.deepcopy(self.automations[key])
   self.writes.append((method,path));del self.automations[key];return {'result':'ok'}
  if path.startswith('/config/config_entries/entry/'):
   key=path.rsplit('/',1)[-1];self.writes.append((method,path));self.entries=[e for e in self.entries if e['entry_id']!=key]
   if self.lose:self.lose=False;raise TimeoutError('lost DELETE response')
   return {'require_restart':False}
  if path.startswith('/services/'):
   self.writes.append((method,path));return []
  raise AssertionError(path)
 def supervisor(self,path,method='GET',payload=None,**kw):
  if self.failbackup:raise RuntimeError('backup failure secret')
  if method=='POST':
   self.backups.append({'slug':'backup123','name':payload['name']});return {'slug':'backup123'}
  if path=='/addons/self/info':return {'slug':'local_agent_123_domotique'}
  if path=='/backups':return {'backups':self.backups}
  if path.endswith('/info'):return {**self.backups[0],'type':'full','homeassistant':'2026.10','homeassistant_exclude_database':False,'size':12,'addons':[{'slug':'local_agent_123_domotique'}]}
  raise AssertionError(path)
 def prepare(self):return self.engine.command({'operation':'prepare','operationId':self.operation,'ownerScope':self.owner})
 def execute(self,preview):
  with patch.object(m.threading,'Thread') as thread:
   result=self.engine.command({'operation':'execute','operationId':self.operation,'ownerScope':self.owner,'previewHash':preview['previewHash'],'confirmation':'RECOMMENCER'})
  m._WORKERS.pop(str(self.engine.path),None)
  self.engine.work(self.operation)
  return self.engine.load()
 def test_non_admin_prepare_has_no_backup_or_write(self):
  self.engine.authorize=lambda:{'is_admin':False}
  with self.assertRaisesRegex(RuntimeError,'droits Home Assistant'):self.prepare()
  self.assertEqual(self.writes,[]);self.assertEqual(self.backups,[]);self.assertFalse(self.engine.path.exists())
 def test_permission_revoked_before_execute_has_no_backup_or_write(self):
  preview=self.prepare();self.engine.authorize=lambda:{'is_admin':False}
  with self.assertRaisesRegex(RuntimeError,'droits Home Assistant'):self.execute(preview)
  self.assertEqual(self.writes,[]);self.assertEqual(self.backups,[])
 def test_worker_rechecks_permission_before_backup(self):
  preview=self.prepare()
  with patch.object(m.threading,'Thread'):
   self.engine.command({'operation':'execute','operationId':self.operation,'ownerScope':self.owner,'previewHash':preview['previewHash'],'confirmation':'RECOMMENCER'})
  m._WORKERS.pop(str(self.engine.path),None);self.engine.authorize=lambda:{'is_admin':False};self.engine.work(self.operation)
  self.assertEqual(self.writes,[]);self.assertEqual(self.backups,[])
 def test_permission_revoked_during_backup_never_removes_automations(self):
  preview=self.prepare();verify=self.engine.verify_archive
  def revoke(slug):
   self.engine.authorize=lambda:{'is_admin':False}
   return verify(slug)
  self.engine.verify_archive=revoke;state=self.execute(preview)
  self.assertEqual(state['state'],'partial');self.assertEqual(self.writes,[])
 def test_backup_failure_has_no_equipment_or_automation_mutation(self):
  preview=self.prepare();self.failbackup=True;state=self.execute(preview)
  self.assertEqual(state['state'],'backup_uncertain');self.assertEqual(self.writes,[]);self.assertFalse(state['backupVerified']);self.assertNotIn('secret',str(state))
 def test_full_reset_preserves_cloud_weather_history_and_is_idempotent(self):
  preview=self.prepare();self.assertEqual([e['entryId'] for e in preview['entries']],['micro1'])
  state=self.execute(preview);self.assertEqual(state['state'],'completed');self.assertTrue(state['backupVerified'])
  self.assertEqual({e['domain'] for e in self.entries},{'cloud','met'});self.assertEqual(self.automations,{})
  writes=list(self.writes);self.execute(preview);self.assertEqual(writes,self.writes);self.assertEqual(len(self.backups),1)
 def test_stale_or_changed_preview_never_writes(self):
  preview=self.prepare();self.now=2000
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.writes,[])
  self.now=1000;self.entries.append({'entry_id':'second','domain':'tuya','title':'New'})
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.writes,[]);self.assertEqual(self.backups,[])
 def test_lost_delete_response_requires_explicit_resume_and_no_double_delete(self):
  preview=self.prepare();self.lose=True;state=self.execute(preview)
  self.assertEqual(state['state'],'partial');self.assertTrue(m.blocks_mutations(Path(self.temp.name)))
  # Status only reports interruption, it cannot perform any DELETE.
  writes=list(self.writes);self.engine.command({'operation':'status','ownerScope':self.owner});self.assertEqual(writes,self.writes)
  resumed=self.prepare();state=self.execute(resumed)
  self.assertEqual(state['state'],'completed');self.assertEqual(len([w for w in self.writes if w[1].endswith('/micro1')]),1);self.assertEqual(len(self.backups),1)
 def test_owner_mismatch_or_bad_confirmation_rejected(self):
  preview=self.prepare()
  with self.assertRaises(RuntimeError):self.engine.command({'operation':'status','ownerScope':'2'*64})
  with self.assertRaises(RuntimeError):self.engine.command({'operation':'execute','operationId':self.operation,'ownerScope':self.owner,'previewHash':preview['previewHash'],'confirmation':True})
  self.assertEqual(self.writes,[])
 def test_configuration_change_while_backup_runs_prevents_deletion(self):
  preview=self.prepare();real=self.engine.verify_archive
  def alter(slug):self.entries.append({'entry_id':'other','domain':'tuya','title':'Late'});return real(slug)
  self.engine.verify_archive=alter;state=self.execute(preview)
  self.assertEqual(state['state'],'partial');self.assertEqual(self.writes,[])
 def test_unsupported_automation_blocks_reset(self):
  self.automations['rule1']['id']='wrong'
  preview=self.prepare();self.assertTrue(preview['blockedReasons'])
  with self.assertRaises(RuntimeError):self.execute(preview)
  self.assertEqual(self.writes,[])
 def test_new_owner_can_replace_readonly_preview_without_old_data(self):
  first=self.prepare();new_op=str(uuid.uuid4())
  fresh=self.engine.command({'operation':'prepare','operationId':new_op,'ownerScope':'2'*64})
  self.assertEqual(fresh['operationId'],new_op);self.assertEqual(fresh['state'],'prepared')
  self.assertNotEqual(fresh['previewHash'],first['previewHash']);self.assertEqual(self.writes,[])
  self.assertTrue((Path(self.temp.name)/('installation-reset-'+self.operation+'.json')).exists())
 def test_new_owner_can_only_prepare_fresh_after_terminal_run(self):
  preview=self.prepare();self.execute(preview)
  next_op=str(uuid.uuid4())
  result=self.engine.command({'operation':'prepare','operationId':next_op,'ownerScope':'2'*64})
  self.assertEqual(result['operationId'],next_op);self.assertFalse(result['backupVerified'])
  self.assertNotIn('backupSlug',result);self.assertEqual(result['removedEntryIds'],[])
  self.assertTrue((Path(self.temp.name)/('installation-reset-'+self.operation+'.json')).exists())
 def test_expired_preview_explicit_prepare_refreshes_hash(self):
  first=self.prepare();self.now=3000;second=self.prepare()
  self.assertGreater(second['expiresAt'],first['expiresAt']);self.assertNotEqual(first['previewHash'],second['previewHash'])
  with self.assertRaises(RuntimeError):self.execute(first)
  self.assertEqual(self.writes,[])
 def test_unverified_archive_prevents_deletion(self):
  preview=self.prepare();self.engine.verify_archive=lambda slug:{'verified':False}
  self.assertEqual(self.execute(preview)['state'],'backup_uncertain');self.assertEqual(self.writes,[])

class ArchiveVerificationTests(unittest.TestCase):
 def archive(self, corrupt=False):
  def tar_bytes(files, mode):
   out=io.BytesIO()
   with tarfile.open(fileobj=out,mode=mode) as archive:
    for name,body in files.items():
     info=tarfile.TarInfo(name);info.size=len(body);archive.addfile(info,io.BytesIO(body))
   return out.getvalue()
  inner=tar_bytes({'data/configuration.yaml':b'default_config:'},'w:gz')
  if corrupt:inner=inner[:-8]+b'broken!!'
  metadata={'slug':'abc123','type':'full','homeassistant':{'version':'2026.10','exclude_database':False},'addons':[{'slug':'local_agent'}]}
  return tar_bytes({'./backup.json':json.dumps(metadata).encode(),'./homeassistant.tar.gz':inner,'./local_agent.tar.gz':tar_bytes({'data/agent-state.json':b'{}'},'w:gz')},'w')
 def test_real_supervisor_style_archive_nested_crc_and_self_addon(self):
  response=io.BytesIO(self.archive())
  with patch('urllib.request.urlopen',return_value=response):proof=m.verify_supervisor_archive('abc123','token')
  self.assertTrue(proof['verified']);self.assertEqual(proof['addons'],['local_agent']);self.assertGreater(proof['bytes'],1024)
 def test_corrupt_inner_archive_prevents_verified_backup(self):
  response=io.BytesIO(self.archive(corrupt=True))
  with patch('urllib.request.urlopen',return_value=response):
   with self.assertRaises(Exception):m.verify_supervisor_archive('abc123','token')
 def test_mismatched_backup_metadata_rejected(self):
  response=io.BytesIO(self.archive())
  with patch('urllib.request.urlopen',return_value=response):
   with self.assertRaises(RuntimeError):m.verify_supervisor_archive('wrong','token')

if __name__=='__main__':unittest.main()
