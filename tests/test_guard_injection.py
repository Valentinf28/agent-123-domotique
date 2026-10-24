import unittest
import test_update_recovery as base
class SecureRecoveryGuardTests(base.RecoveryTests):
 def proof(self,*args):
  self.assertEqual(args,('fresh',self.owner,self.slug))
  return {'verified':True,'authenticated':True,'cipherVersion':3,'newBackup':True,'backupId':'fresh','ownerScope':self.owner,'sha256':'a'*64,'bytes':2048,'addons':[self.slug]}
 def test_protected_without_verifier_keeps_journal(self):
  self.backup['protected']=True
  with self.assertRaises(RuntimeError):self.commit(self.preview())
  self.assertEqual(self.engine.load(),self.old)
 def test_protected_new_archive_proof_retires_only_after_full_checks(self):
  self.backup['protected']=True;self.engine.verify_recovery_archive=self.proof
  self.assertTrue(self.commit(self.preview())['oldJournalArchived'])
 def test_mismatched_scope_or_non_new_proof_never_retires(self):
  self.backup['protected']=True
  for patch in [{'ownerScope':'b'*64},{'authenticated':False},{'newBackup':False},{'cipherVersion':2},{'backupId':'another'},{'sha256':'bad'}]:
   self.engine.verify_recovery_archive=lambda *args,p=patch:self.proof(*args)|p
   with self.subTest(patch=patch),self.assertRaises(RuntimeError):self.commit(self.preview())
   self.assertEqual(self.engine.load(),self.old)
if __name__=='__main__':unittest.main()
