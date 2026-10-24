import hashlib, io, json, os, tarfile, tempfile, unittest, uuid, fcntl
from pathlib import Path
from securetar import SecureTarArchive
from native_backup_export import NativeBackupExportWorker, ExportRejected, read_private, CHUNK_BYTES, MAX_BYTES
NOW=1800000000
EXP='2030-01-01T00:00:00+00:00'
ADDON='local_agent_123_domotique'
FOLDERS=['addons/local','media','share','ssl']
def job(mode='create_full'):
 return dict(protocol=1,exportId=str(uuid.uuid4()),nonce='1'*32,bindingGeneration='2'*64,ownerScope='3'*64,mode=mode,backupId='fixture1' if mode=='existing' else None,maxBytes=MAX_BYTES,chunkBytes=CHUNK_BYTES,maxLocalBackups=6,expiresAt=EXP)
def archive(password):
 data=io.BytesIO(); metadata=dict(slug='fixture1',type='full',protected=True,homeassistant={'exclude_database':False},addons=[{'slug':ADDON}],folders=FOLDERS)
 with SecureTarArchive(fileobj=data,mode='w',password=password,create_version=3) as a:
  raw=json.dumps(metadata).encode();m=tarfile.TarInfo('backup.json');m.size=len(raw);a.tar.addfile(m,io.BytesIO(raw))
  for name in ['homeassistant',ADDON,*FOLDERS,'supervisor']:
   with a.create_tar(name.replace('/','_')+'.tar.gz',gzip=True) as inner:
    raw=b'private-fixture';m=tarfile.TarInfo('data/fixture');m.size=len(raw);inner.addfile(m,io.BytesIO(raw))
 return data.getvalue()
class Supervisor:
 def __init__(self): self.calls=[];self.raw=None;self.marker=None;self.lose_create=False;self.delay_listing=False;self.info_type='full'
 async def json(self,method,path,body=None):
  self.calls.append((method,path))
  if path=='/addons/self/info':return {'slug':ADDON}
  if path=='/addons':return {'addons':[{'slug':ADDON}]}
  if path=='/backups/new/full':
   self.marker=body['name'];self.raw=archive(body['password'])
   if self.lose_create:raise ConnectionError('fixture disconnect')
   return {'job_id':'nativejob'}
  if path=='/backups':return {'backups':[] if self.delay_listing or self.marker is None else [{'slug':'fixture1','name':self.marker}]}
  if path=='/backups/fixture1/info':return dict(type=self.info_type,protected=True,size_bytes=len(self.raw),folders=FOLDERS)
  raise AssertionError(path)
 async def download(self,slug):
  for offset in range(0,len(self.raw),CHUNK_BYTES):yield self.raw[offset:offset+CHUNK_BYTES]
class Portal:
 def __init__(self,j):self.j=j;self.state='queued';self.offset=0;self.data=bytearray();self.posts=[];self.kits=[];self.input=None;self.request=None;self.binding=j['bindingGeneration'];self.lose_put=False
 async def status(self,j):return dict(state=self.state,offset=self.offset,bindingGeneration=self.binding,expiresAt=EXP,recoveryRequest=self.request,maxLocalBackups=self.j['maxLocalBackups'])
 async def post(self,j,body):
  self.posts.append(body)
  if body['phase']=='complete':self.state='ready'
 async def put(self,j,offset,data,digest):
  assert offset==self.offset and hashlib.sha256(data).hexdigest()==digest
  self.data.extend(data);self.offset+=len(data)
  if self.lose_put:self.lose_put=False;raise ConnectionError('fixture disconnect after acknowledgement')
  return {'offset':self.offset}
 async def recovery_input(self,j):value,self.input=self.input,None;return value
 async def recovery_kit(self,j,nonce,raw):self.kits.append((nonce,raw))
class WorkerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.j=job();self.s=Supervisor();self.p=Portal(self.j);self.w=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW)
 async def asyncTearDown(self):self.tmp.cleanup()
 async def test_roundtrip_only_native_encrypted_and_owner_context(self):
  result=await self.w.tick(self.j);self.assertEqual(result['state'],'ready');self.assertEqual(bytes(self.p.data),self.s.raw)
  self.assertNotIn(b'private-fixture',self.s.raw);self.assertEqual(self.p.kits,[])
  for path in self.root.glob('*'):self.assertEqual(path.stat().st_mode & 0o077,0)
  context=self.w.recovery_archive_context('fixture1','3'*64);self.assertTrue(context['newBackup']);self.assertEqual(context['ownerScope'],'3'*64)
  self.assertIsNone(self.w.recovery_archive_context('fixture1','2'*64))
  self.assertTrue(all(path not in ('/backups/options','/backups/config/info','/backups/restore') for _,path in self.s.calls))
 async def test_self_stop_uncertain_create_reuses_key_and_never_recreates(self):
  self.s.lose_create=True
  with self.assertRaises(ConnectionError):await self.w.tick(self.j)
  before=(self.root/(self.j['exportId']+'.key.json')).read_bytes()
  restarted=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW)
  self.assertEqual((await restarted.tick(self.j))['state'],'ready')
  self.assertEqual(before,(self.root/(self.j['exportId']+'.key.json')).read_bytes())
  self.assertEqual(sum(path=='/backups/new/full' for _,path in self.s.calls),1)
 async def test_no_duplicate_when_native_listing_delayed(self):
  self.s.delay_listing=True
  self.assertEqual((await self.w.tick(self.j))['state'],'creating')
  self.assertEqual((await self.w.tick(self.j))['state'],'creating')
  self.assertEqual(sum(path=='/backups/new/full' for _,path in self.s.calls),1)
 async def test_binding_change_refuses_before_native_call(self):
  self.p.binding='4'*64
  with self.assertRaisesRegex(ExportRejected,'BINDING_CHANGED'):await self.w.tick(self.j)
  self.assertEqual(self.s.calls,[])
 async def test_cancel_refuses_before_native_call(self):
  self.p.state='cancelled'
  with self.assertRaisesRegex(ExportRejected,'CANCELLED'):await self.w.tick(self.j)
  self.assertEqual(self.s.calls,[])
 async def test_second_job_refused_during_native_creation(self):
  self.s.delay_listing=True;await self.w.tick(self.j)
  second=job();self.assertEqual((await self.w.tick(second))['state'],'busy')
 async def test_resume_after_lost_put_ack_no_duplicate_bytes(self):
  self.p.lose_put=True
  with self.assertRaises(ConnectionError):await self.w.tick(self.j)
  self.assertEqual((await self.w.tick(self.j))['state'],'ready');self.assertEqual(bytes(self.p.data),self.s.raw)
 async def test_existing_requests_key_and_rejects_wrong_key(self):
  self.j=job('existing');self.p=Portal(self.j);self.w=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW);self.s.raw=archive('fixture-password-not-real-secret-1234567890')
  self.assertEqual((await self.w.tick(self.j))['state'],'awaiting_key');self.assertEqual(self.p.data,b'')
  self.p.input=b'wrong-password-1234567890'
  self.assertEqual((await self.w.tick(self.j))['state'],'awaiting_key');self.assertFalse((self.root/(self.j['exportId']+'.key.json')).exists())
  self.p.input=b'Native backup password: fixture-password-not-real-secret-1234567890'
  self.assertEqual((await self.w.tick(self.j))['state'],'ready');self.assertIsNone(self.w.recovery_archive_context('fixture1','3'*64))
 async def test_recovery_kit_only_explicit_owner_request(self):
  await self.w.tick(self.j);self.assertEqual(self.p.kits,[])
  self.p.request={'nonce':'5'*32,'expiresAt':EXP}
  await self.w.tick(self.j);self.assertEqual(len(self.p.kits),1);self.assertIn(b'Native backup password:',self.p.kits[0][1])
 async def test_partial_backup_rejected(self):
  self.s.info_type='partial'
  with self.assertRaisesRegex(ExportRejected,'NATIVE_BACKUP_NOT_ENCRYPTED_FULL'):await self.w.tick(self.j)
  self.assertEqual(self.p.data,b'')
 async def test_modified_job_refused(self):
  self.s.delay_listing=True;await self.w.tick(self.j)
  modified={**self.j,'nonce':'6'*32}
  with self.assertRaisesRegex(ExportRejected,'JOB_CHANGED'):await self.w.tick(modified)
 async def test_wire_job_mutable_status_and_numeric_expiry(self):
  await self.w.tick(self.j)
  later={**self.j,'state':'ready','offset':len(self.s.raw),'backupId':'fixture1','expiresAt':1893456000000}
  self.p.request={'nonce':str(uuid.uuid4()),'expiresAt':1893456000000}
  self.assertEqual((await self.w.tick(later))['state'],'ready');self.assertEqual(len(self.p.kits),1)
 async def test_missing_private_archive_context_returns_none(self):
  await self.w.tick(self.j);(self.root/(self.j['exportId']+'.tar')).unlink()
  self.assertIsNone(self.w.recovery_archive_context('fixture1','3'*64))
 async def test_finished_local_copies_purge_without_native_delete(self):
  await self.w.tick(self.j)
  w=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW+25*3600);w.purge_expired()
  self.assertFalse((self.root/(self.j['exportId']+'.tar')).exists());self.assertTrue((self.root/(self.j['exportId']+'.key.json')).exists())
  self.assertFalse(any(method=='DELETE' for method,path in self.s.calls))
 async def test_missing_backup_id_not_stringified_none(self):
  self.j=job('existing');self.j['backupId']=None
  with self.assertRaisesRegex(ExportRejected,'INVALID_JOB'):await self.w.tick(self.j)
 async def test_cancel_during_native_download_uploads_nothing(self):
  original=self.s.download
  async def download(slug):
   async for chunk in original(slug):
    self.p.state='cancelled';yield chunk
  self.s.download=download
  with self.assertRaisesRegex(ExportRejected,'CANCELLED'):await self.w.tick(self.j)
  self.assertEqual(self.p.data,b'')
 async def test_shared_maintenance_lock_prevents_native_call(self):
  with open(self.root/'maintenance.lock','w') as locked:
   os.chmod(locked.name,0o600);fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.assertEqual((await self.w.tick(self.j))['state'],'busy');self.assertEqual(self.s.calls,[])
 async def test_native_busy_does_not_create_backup(self):
  async def busy():return True
  self.w.maintenance_busy=busy
  self.assertEqual((await self.w.tick(self.j))['state'],'busy');self.assertEqual(self.s.calls,[])
 async def test_cancelled_active_journal_retires_only_after_native_idle(self):
  self.s.delay_listing=True;await self.w.tick(self.j);self.assertTrue(self.w.busy());self.p.state='cancelled'
  async def busy():return True
  self.w.maintenance_busy=busy
  self.assertEqual((await self.w.tick(self.j))['state'],'busy');self.assertTrue(self.w.busy())
  async def idle():return False
  self.w.maintenance_busy=idle
  with self.assertRaisesRegex(ExportRejected,'CANCELLED'):await self.w.tick(self.j)
  self.assertFalse(self.w.busy());self.assertTrue(self.s.raw)
 async def test_expired_temp_copy_keeps_key_for_existing_export(self):
  await self.w.tick(self.j)
  later=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW+25*3600);later.purge_expired()
  newer=job('existing');self.p=Portal(newer)
  later=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW+25*3600)
  self.assertEqual((await later.tick(newer))['state'],'ready');self.assertIsNone(self.p.input)
 async def test_restart_and_immediate_new_job_reconciles_cancelled_prior(self):
  self.s.delay_listing=True;await self.w.tick(self.j);self.s.delay_listing=False
  prior=self.j['exportId'];newer=job();self.p=Portal(newer);base_status=self.p.status
  async def status(j):
   result=await base_status(j)
   if j['exportId']==prior:result.update(state='cancelled')
   return result
  self.p.status=status
  async def idle():return False
  restarted=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW,maintenance_busy=idle)
  self.assertEqual((await restarted.tick(newer))['state'],'ready')
  self.assertEqual(read_private(self.root/(prior+'.json'))['phase'],'cancelled_safe')
 async def test_native_backup_count_respects_supplied_policy_without_deleting(self):
  self.j['maxLocalBackups']=1;self.s.marker='existing fixture'
  with self.assertRaisesRegex(ExportRejected,'NATIVE_BACKUP_LIMIT'):await self.w.tick(self.j)
  self.assertFalse(any(method=='POST' or method=='DELETE' for method,path in self.s.calls))
  self.assertIn({'phase':'failed','code':'native_limit'},self.p.posts)
 async def test_real_short_native_key_verifies_without_length_guess(self):
  self.j=job('existing');self.p=Portal(self.j);self.s.raw=archive('short');self.p.input=b'short'
  self.w=NativeBackupExportWorker(self.root,self.s,self.p,clock=lambda:NOW)
  self.assertEqual((await self.w.tick(self.j))['state'],'ready')
 async def test_changed_installed_inventory_refuses_upload(self):
  original=self.s.json;calls=0
  async def json_call(method,path,body=None):
   nonlocal calls
   result=await original(method,path,body)
   if path=='/addons':
    calls+=1
    if calls>1:result={'addons':[{'slug':ADDON},{'slug':'new_addon'}]}
   return result
  self.s.json=json_call
  with self.assertRaisesRegex(ExportRejected,'NATIVE_INVENTORY_CHANGED'):await self.w.tick(self.j)
  self.assertEqual(self.p.data,b'')
 async def test_changed_quota_is_rechecked_before_native_create(self):
  self.s.marker='existing native backup';original=self.s.json
  async def json_call(method,path,body=None):
   result=await original(method,path,body)
   if path=='/backups':self.p.j['maxLocalBackups']=1
   return result
  self.s.json=json_call
  with self.assertRaisesRegex(ExportRejected,'NATIVE_BACKUP_LIMIT'):await self.w.tick(self.j)
  self.assertFalse(any(method=='POST' for method,path in self.s.calls))
 async def test_quota_change_does_not_invalidate_ready_key_download(self):
  await self.w.tick(self.j);later={**self.j,'maxLocalBackups':2}
  self.p.request={'nonce':str(uuid.uuid4()),'expiresAt':EXP}
  self.assertEqual((await self.w.tick(later))['state'],'ready')
 async def test_symlink_private_path_refused(self):
  target=self.root/'outside';target.write_text('{}');(self.root/(self.j['exportId']+'.json')).symlink_to(target)
  with self.assertRaises(OSError):await self.w.tick(self.j)
if __name__=='__main__':unittest.main()
