import unittest,tempfile,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from factory_stage import command
U='11111111-1111-1111-1111-111111111111';R='22222222-2222-2222-2222-222222222222';O='a'*64
class Reset:
 def __init__(self):self.previous={'state':'completed','backupVerified':True,'operationId':R,'ownerScope':O,'backupSlug':'backup'};self.entries=[];self.backup=True
 def require_admin(self):pass
 def load(self):return self.previous
 def snapshot(self):return {'entries':self.entries,'automations':[],'blockedReasons':[],'preservedEntries':[{'domain':'webdav','entryId':'old-backup'}]}
 def verify_archive(self,slug):return {'verified':self.backup}
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name);(self.data/'agent-state.json').write_text('{"token":"old"}');self.options={'enrollment_code':'OLD','restore_identity':'OLD','relay_house_id':'old','relay_token':'old','pool_camera_enabled':True};self.calls=[];self.reset=Reset();self.body={'operation':'factory_prepare','operationId':U,'resetOperationId':R,'ownerScope':O,'factoryId':'factory_'+'b'*32,'factoryToken':'c'*64,'confirmed':True}
 def supervisor(self,path,**kwargs):
  self.calls.append((path,kwargs));
  if path.endswith('/options'):self.options=kwargs['payload']['options'];return {}
  return {'options':self.options}
 def call(self,path,**kw):self.calls.append((path,kw));return [{'entry_id':'old-backup'}] if path=='/config/config_entries/entry' else {'require_restart':False}
 def run_stage(self,body):return command(body,self.reset,self.supervisor,self.call,data=self.data,restart=False,now=100)
 def test_stages_options_without_losing_identity_then_commits(self):
  (self.data/'agent-state.json').write_text('{"token":"old"}');(self.data/'pool-private').mkdir();(self.data/'pool-private'/'photo').write_text('private');(self.data/'options.json').write_text('{}')
  before=self.run_stage(self.body);self.assertEqual(before['state'],'prepared');self.assertEqual(json.loads((self.data/'agent-state.json').read_text())['token'],'old');self.assertNotIn('factoryToken',before);self.assertEqual(self.options['relay_token'],'')
  commit={'operation':'factory_commit','operationId':U,'ownerScope':O,'confirmed':True};out=self.run_stage(commit);self.assertEqual(out['state'],'committed');self.assertFalse((self.data/'agent-state.json').exists());self.assertFalse((self.data/'pool-private').exists());self.assertTrue((self.data/'options.json').exists());self.assertEqual(self.run_stage(commit),out);self.assertNotIn('c'*64,(self.data/'factory-stage.json').read_text())
 def test_no_cleanup_without_completed_backup_and_correct_owner(self):
  for key,value in [('backupVerified',False),('state','partial'),('operationId','wrong'),('ownerScope','f'*64)]:
   self.reset.previous[key]=value
   with self.assertRaises(RuntimeError):self.run_stage(self.body)
   self.reset=Reset()
  self.reset.backup=False
  with self.assertRaises(RuntimeError):self.run_stage(self.body)
  self.assertFalse((self.data/'factory-stage.json').exists())
 def test_equipment_reappearing_blocks_commit(self):
  self.run_stage(self.body);self.reset.entries=[{'entryId':'new'}]
  with self.assertRaises(RuntimeError):self.run_stage({'operation':'factory_commit','operationId':U,'ownerScope':O,'confirmed':True})
 def test_commit_requires_exact_staged_owner_confirmation(self):
  self.run_stage(self.body)
  for patch in [{'ownerScope':'f'*64},{'confirmed':False},{'operationId':R}]:
   with self.assertRaises((RuntimeError,ValueError)):self.run_stage({'operation':'factory_commit','operationId':U,'ownerScope':O,'confirmed':True,**patch})
 def test_old_background_identity_cannot_return_after_commit(self):
  from factory_stage import retired_identity
  self.run_stage(self.body);self.run_stage({'operation':'factory_commit','operationId':U,'ownerScope':O,'confirmed':True})
  self.assertTrue(retired_identity({'token':'old'},self.data));self.assertFalse(retired_identity({'token':'new'},self.data));self.assertFalse(retired_identity({'pending_factory_activation':{'token':'new'}},self.data))
 def test_lost_options_response_reconciles_same_preparation(self):
  def lost(path,**kw):
   value=self.supervisor(path,**kw)
   if path.endswith('/options'):raise TimeoutError()
   return value
  with self.assertRaises(TimeoutError):command(self.body,self.reset,lost,self.call,data=self.data,restart=False,now=100)
  self.assertEqual(self.run_stage(self.body)['state'],'prepared')
if __name__=='__main__':unittest.main()
