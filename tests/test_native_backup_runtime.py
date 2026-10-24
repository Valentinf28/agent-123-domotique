import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import native_backup_runtime as runtime

class FakeWorker:
 def __init__(self,root,*args,**kwargs):
  self.root=Path(root);self.root.mkdir(exist_ok=True);self.calls=[];self.started=threading.Event();self.release=threading.Event();self.fail=False
 @contextmanager
 def locked(self):yield True
 def purge_expired(self):pass
 def recovery_archive_context(self,*args):return None
 async def tick(self,job):
  self.calls.append(job);self.started.set();self.release.wait(2)
  if self.fail:raise RuntimeError('secret-must-not-log')
  p=self.root/(job['exportId']+'.json');p.write_text(json.dumps({'phase':'cancelled_safe','job':job}));p.chmod(0o600)
  return {'state':'cancelled_safe'}

class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
  self.patch=patch.object(runtime,'NativeBackupExportWorker',FakeWorker);self.patch.start();self.addCleanup(self.patch.stop)
  self.job={'exportId':'11111111-1111-4111-8111-111111111111','nonce':'a'*32}
 def make(self,report=None):return runtime.NativeBackupRuntime('https://client.labox.eco/api',lambda:'fixture',lambda:'fixture',lambda:{'success':True,'result':{'state':'idle'}},data=self.data,report=report)
 def test_active_worker_does_not_block_heartbeat_or_duplicate(self):
  r=self.make();start=time.monotonic();r.submit(self.job);self.assertLess(time.monotonic()-start,0.5);self.assertTrue(r.worker.started.wait(1));r.submit(self.job);r.worker.release.set();r._thread.join(2);self.assertEqual(len(r.worker.calls),1)
 def test_missing_server_job_reconciles_saved_pending_after_restart(self):
  folder=self.data/'native-backup-exports';folder.mkdir();p=folder/(self.job['exportId']+'.json');p.write_text(json.dumps({'phase':'creating','job':self.job}));p.chmod(0o600)
  r=self.make();r.worker.release.set();r.submit(None);r._thread.join(2);self.assertEqual(r.worker.calls,[self.job]);self.assertIsNone(r._job)
 def test_new_job_does_not_hide_unsettled_previous_job(self):
  r=self.make();r.submit(self.job);self.assertTrue(r.worker.started.wait(1));r.submit({'exportId':'22222222-2222-4222-8222-222222222222'});self.assertEqual(r._job,self.job);r.worker.release.set();r._thread.join(2)
 def test_exception_logging_never_contains_native_detail(self):
  log=[];r=self.make(log.append);r.worker.fail=True;r.worker.release.set();r.submit(self.job);r._thread.join(2);self.assertTrue(log);self.assertNotIn('secret-must-not-log',' '.join(log))
if __name__=='__main__':unittest.main()
