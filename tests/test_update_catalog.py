import json
import threading
import unittest
import urllib.error
from unittest.mock import patch
import installation_update as updates
import test_installation_update as baseline

class CatalogTests(unittest.TestCase):
 setUp=baseline.UpdateTests.setUp
 new_engine=baseline.UpdateTests.new_engine
 call=baseline.UpdateTests.call
 supervisor=baseline.UpdateTests.supervisor
 execute=baseline.UpdateTests.execute
 def start(self):
  self.refreshes=0
  def refresh():self.refreshes+=1;self.latest='0.6.1'
  self.engine.refresh_catalog=refresh
  original=self.engine.call
  def call(path,**kwargs):
   if path=='/services/homeassistant/update_entity':
    self.assertEqual(kwargs['payload'],{'entity_id':'update.agent_labo'});return []
   return original(path,**kwargs)
  self.engine.call=call
  with patch('installation_update.threading.Thread'):
   result=self.engine.command(self.base|{'operation':'prepare'})
  return result
 def finish(self):
  self.engine.prepare_catalog(self.operation)
  return self.engine.command({'operation':'status','ownerScope':self.base['ownerScope']})
 def test_stale_catalog_is_refreshed_before_preview_without_install(self):
  self.latest='0.6.0';initial=self.start()
  self.assertEqual(initial['state'],'refreshing_catalog');self.assertNotIn('previewHash',initial);self.assertTrue(updates.busy(self.data))
  ready=self.finish();self.assertEqual(ready['state'],'prepared');self.assertIn('previewHash',ready);self.assertEqual(self.refreshes,1)
  self.assertEqual(self.installs,[]);self.assertEqual(self.backups,[])
  self.assertEqual(self.engine.command(self.base|{'operation':'prepare'})['previewHash'],ready['previewHash']);self.assertEqual(self.refreshes,1)
  final=self.execute(ready);self.assertEqual(len(self.installs),1);self.assertEqual(len(self.backups),1);self.assertEqual(final['state'],'awaiting_restart')
 def test_refresh_timeout_or_permission_failure_never_backups_or_installs(self):
  for exc in (TimeoutError(),RuntimeError('denied')):
   self.start()
   def fail():raise exc
   self.engine.refresh_catalog=fail
   self.assertEqual(self.finish()['state'],'failed');self.assertEqual(self.installs,[]);self.assertEqual(self.backups,[])
   self.engine.path.unlink()
 def test_restart_during_refresh_stops_without_replaying(self):
  self.start();updates._WORKERS.pop(str(self.engine.path),None);self.engine=self.new_engine()
  self.assertEqual(self.engine.command({'operation':'status','ownerScope':self.base['ownerScope']})['state'],'failed');self.assertEqual(self.refreshes,0);self.assertEqual(self.installs,[])
 def test_catalog_newer_than_approved_target_stops(self):
  self.start();self.engine.refresh_catalog=lambda:setattr(self,'latest','0.6.2')
  self.assertEqual(self.finish()['state'],'failed');self.assertEqual(self.installs,[])
 def test_wrong_source_changed_during_refresh_stops(self):
  self.start();self.engine.refresh_catalog=lambda:setattr(self,'repo','unknown')
  self.assertEqual(self.finish()['state'],'failed');self.assertEqual(self.installs,[])
 def test_automatic_updates_enabled_during_refresh_stop(self):
  self.start();self.engine.refresh_catalog=lambda:setattr(self,'auto',True)
  self.assertEqual(self.finish()['state'],'failed');self.assertEqual(self.installs,[])
 def test_execute_cannot_skip_pending_catalog(self):
  self.start()
  with self.assertRaises(ValueError):self.engine.command(self.base|{'operation':'execute','confirmed':True,'previewHash':'b'*64})
  self.assertEqual(self.installs,[]);updates._WORKERS.pop(str(self.engine.path),None)
 def test_no_admin_cannot_refresh(self):
  self.engine.authorize=lambda:{'is_admin':False}
  with self.assertRaises(RuntimeError):self.start()
  self.assertEqual(self.refreshes,0);self.assertEqual(self.installs,[])
 def test_server_error_after_submission_stays_busy_until_observed(self):
  preview=baseline.UpdateTests.prepare(self);original=self.engine.call
  def fail(path,**kw):
   if path=='/services/update/install':raise urllib.error.HTTPError('url',500,'error',{},None)
   return original(path,**kw)
  self.engine.call=fail;state=self.execute(preview)
  self.assertEqual(state['state'],'awaiting_restart');self.assertTrue(updates.busy(self.data));self.assertTrue(state['installSubmitted'])
  self.running=self.installed='0.6.1';self.engine=self.new_engine()
  self.assertEqual(self.engine.command({'operation':'status','ownerScope':self.base['ownerScope']})['state'],'completed')
 def test_previous_owner_terminal_journal_is_archived_once_before_refresh(self):
  preview=baseline.UpdateTests.prepare(self);self.execute(preview);self.running=self.installed='0.6.1';self.engine=self.new_engine()
  self.engine.command({'operation':'status','ownerScope':self.base['ownerScope']})
  self.base['ownerScope']='2'*64;self.base['targetVersion']='0.6.2';self.latest='0.6.2'
  original=self.engine.preflight
  def fail(*a,**kw):raise RuntimeError('temporary native failure')
  self.engine.preflight=fail
  with self.assertRaises(RuntimeError):self.engine.command(self.base|{'operation':'prepare'})
  self.assertEqual(self.engine.load(),{});self.assertTrue((self.data/('installation-update-'+self.operation+'.json')).exists())
  self.engine.preflight=original;self.assertEqual(self.engine.command(self.base|{'operation':'prepare'})['state'],'prepared')
 def test_slow_catalog_returns_immediately_and_blocks_concurrent_reset(self):
  started=threading.Event();finish=threading.Event()
  def refresh():started.set();finish.wait(2)
  self.engine.refresh_catalog=refresh;original=self.engine.call
  self.engine.call=lambda path,**kw:[] if path=='/services/homeassistant/update_entity' else original(path,**kw)
  try:
   result=self.engine.command(self.base|{'operation':'prepare'})
   self.assertEqual(result['state'],'refreshing_catalog');self.assertTrue(started.wait(1));worker=updates._WORKERS[str(self.engine.path)]
   self.assertTrue(updates.busy(self.data));self.assertEqual(self.engine.command(self.base|{'operation':'prepare'})['state'],'refreshing_catalog')
  finally:finish.set()
  worker.join(2);self.assertEqual(self.engine.load()['state'],'prepared');self.assertEqual(self.installs,[])

if __name__=='__main__':unittest.main()
