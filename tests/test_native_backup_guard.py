import json
from pathlib import Path
import tempfile
import unittest
from native_backup_guard import local_maintenance_busy,export_busy,assert_update_ready,worker_maintenance_busy
class GuardTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.data=Path(self.temp.name);self.read=lambda:{'success':True,'result':{'state':'idle','agent_errors':{}}}
 def put(self,name,state):
  (self.data/name).write_text(json.dumps({'state':state}))
 def test_attention_is_not_treated_as_active_but_uncertain_states_are(self):
  self.put('installation-update.json','attention_required');self.assertFalse(local_maintenance_busy(self.data));self.assertFalse(worker_maintenance_busy(self.read,self.data))
  for state in ['refreshing_catalog','backing_up','backup_uncertain','installing','awaiting_restart','unknown']:
   self.put('installation-update.json',state);self.assertTrue(worker_maintenance_busy(self.read,self.data))
 def test_attention_with_submitted_install_requires_native_update_idle(self):
  (self.data/'installation-update.json').write_text(json.dumps({'state':'attention_required','installSubmitted':True,'entityId':'update.agent'}))
  self.assertTrue(worker_maintenance_busy(self.read,self.data))
  for native in [{'entity_id':'update.agent','state':'on','attributes':{'in_progress':True}}, {'entity_id':'update.agent','state':'unknown','attributes':{'in_progress':False}}, {'entity_id':'update.other','state':'off','attributes':{'in_progress':False}}]:
   self.assertTrue(worker_maintenance_busy(self.read,self.data,lambda e,n=native:n))
  self.assertFalse(worker_maintenance_busy(self.read,self.data,lambda e:{'entity_id':e,'state':'off','attributes':{'in_progress':False}}))
 def test_reset_and_factory_prevent_worker(self):
  for name,state in [('installation-reset.json','partial'),('factory-stage.json','prepared')]:
   self.put(name,state);self.assertTrue(local_maintenance_busy(self.data));(self.data/name).unlink()
 def test_native_backup_requires_positive_idle_proof(self):
  for state in ['creating','restoring',None]:
   self.assertTrue(worker_maintenance_busy(lambda:{'success':True,'result':{'state':state}},self.data))
   with self.assertRaises(RuntimeError):assert_update_ready(lambda:{'success':True,'result':{'state':state}},self.data)
  self.assertTrue(worker_maintenance_busy(lambda:{'success':False},self.data))
  self.assertTrue(worker_maintenance_busy(lambda:{'success':False,'state':'idle'},self.data))
 def test_export_persists_barrier_after_process_restart(self):
  folder=self.data/'native-backup-exports';folder.mkdir();p=folder/'fixture.json'
  for phase in ['planned','creating','created','uploading','unknown']:
   p.write_text(json.dumps({'phase':phase}));self.assertTrue(export_busy(self.data))
   with self.assertRaises(RuntimeError):assert_update_ready(self.read,self.data)
  for phase in ['ready','cancelled_safe','expired_safe','failed_safe']:
   p.write_text(json.dumps({'phase':phase}));self.assertFalse(export_busy(self.data));assert_update_ready(self.read,self.data)
 def test_large_terminal_history_and_retained_keys_do_not_block_update(self):
  folder=self.data/'native-backup-exports';folder.mkdir()
  for i in range(1100):
   (folder/(str(i)+'.json')).write_text(json.dumps({'phase':'ready' if i%2 else 'cancelled_safe'}))
   (folder/(str(i)+'.key.json')).write_text('private fixture key retained')
  self.assertFalse(export_busy(self.data));assert_update_ready(self.read,self.data)
  active=folder/'active.json';active.write_text(json.dumps({'phase':'uploading'}))
  self.assertTrue(export_busy(self.data))
  with self.assertRaises(RuntimeError):assert_update_ready(self.read,self.data)
  active.unlink();self.assertFalse(export_busy(self.data))
 def test_corrupt_journal_fails_closed(self):
  (self.data/'installation-update.json').write_text('not json');self.assertTrue(local_maintenance_busy(self.data))
if __name__=='__main__':unittest.main()

class NativeDispatchGuards(unittest.TestCase):
 def test_system_restart_blocked_on_direct_ws_and_http_paths(self):
  from contextlib import contextmanager
  from unittest.mock import Mock,patch
  import agent
  @contextmanager
  def denied():raise RuntimeError('backup active');yield
  messages=[
   {'action':'ha.services.call','payload':{'domain':'homeassistant','service':'restart','data':{}}},
   {'action':'ha.ws.send','payload':{'tunnelId':'fixture','data':json.dumps({'type':'call_service','domain':'homeassistant','service':'restart'})}},
   {'action':'ha.proxy','payload':{'method':'POST','path':'/api/services/homeassistant/restart','body':''}},
  ]
  upstream=Mock()
  with patch('installation_reset.blocks_mutations',return_value=False),patch.object(agent,'BACKUP_SYSTEM_ACTION',denied),patch.dict(agent.HA_TUNNELS,{'fixture':upstream}),patch.object(agent,'request_json') as request,patch.object(agent.urllib.request,'urlopen') as urlopen:
   for message in messages:self.assertFalse(agent.relay_command('fixture-token',{'id':'fixture',**message})['ok'])
   request.assert_not_called();urlopen.assert_not_called();upstream.send.assert_not_called()
 def test_ordinary_control_does_not_take_system_restart_guard(self):
  from unittest.mock import Mock,patch
  import agent
  guard=Mock(side_effect=RuntimeError('must not run'))
  with patch('installation_reset.blocks_mutations',return_value=False),patch.object(agent,'BACKUP_SYSTEM_ACTION',guard),patch.object(agent,'request_json',return_value=[]):
   result=agent.relay_command('fixture-token',{'id':'fixture','action':'ha.services.call','payload':{'domain':'switch','service':'turn_on','data':{'entity_id':'switch.fixture'}}})
   self.assertTrue(result['ok']);guard.assert_not_called()

class FactoryGuardTests(unittest.TestCase):
 def test_factory_mutations_take_same_maintenance_lock(self):
  from unittest.mock import Mock,patch
  import factory_stage
  import fcntl,os
  with tempfile.TemporaryDirectory() as temporary:
   data=Path(temporary);fd=os.open(data/'installation-maintenance.lock',os.O_CREAT|os.O_RDWR,0o600)
   try:
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch.object(factory_stage,'_command') as actual:
     with self.assertRaises(BlockingIOError):factory_stage.command({'operation':'factory_prepare'},None,None,None,data=data)
     actual.assert_not_called()
   finally:os.close(fd)
   guard=Mock(side_effect=RuntimeError('backup active'))
   with patch.object(factory_stage,'_command') as actual:
    with self.assertRaises(RuntimeError):factory_stage.command({'operation':'factory_commit'},None,None,None,data=data,backup_guard=guard)
    actual.assert_not_called()
