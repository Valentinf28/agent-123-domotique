import hashlib,os
from pathlib import Path
import tempfile,unittest
from recovery_archive_binding import make_recovery_verifier
from recovery_securearchive import ArchiveRejected
from test_recovery_securearchive import fixture,KEY,SLUG,ADDON
class BindingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.path=self.root/'encrypted.tar';self.path.write_bytes(fixture());self.path.chmod(0o600);self.owner='a'*64
  self.context={'backupId':SLUG,'ownerScope':self.owner,'newBackup':True,'encrypted_path':str(self.path),'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),'bytes':self.path.stat().st_size,'password':KEY,'expected_addons':[ADDON],'expected_folders':['ssl','share','media']}
  self.verify=make_recovery_verifier(lambda *_:dict(self.context),self.root)
 def test_private_matching_new_backup_is_verified_without_key_in_proof(self):
  proof=self.verify(SLUG,self.owner,ADDON);self.assertTrue(proof['newBackup']);self.assertTrue(proof['verified']);self.assertNotIn('password',proof);self.assertNotIn('encrypted_path',proof)
 def test_wrong_owner_old_backup_and_wrong_hash_rejected(self):
  for change in ({'ownerScope':'b'*64},{'newBackup':False},{'sha256':'0'*64}):
   original=dict(self.context);self.context.update(change)
   with self.subTest(change=change),self.assertRaises(ArchiveRejected):self.verify(SLUG,self.owner,ADDON)
   self.context=original
 def test_public_file_or_symlink_refused(self):
  self.path.chmod(0o644)
  with self.assertRaises(ArchiveRejected):self.verify(SLUG,self.owner,ADDON)
  self.path.chmod(0o600);link=self.root/'link.tar';link.symlink_to(self.path);self.context['encrypted_path']=str(link)
  with self.assertRaises(ArchiveRejected):self.verify(SLUG,self.owner,ADDON)
if __name__=='__main__':unittest.main()
