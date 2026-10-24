import unittest
from native_backup_transport import FixedTransport,NoRedirect,SupervisorBackupTransport
from native_backup_export import ExportRejected
class TransportTests(unittest.TestCase):
 def test_origins_restrict_credentials_and_arbitrary_hosts(self):
  for value in ['http://client.labox.eco','https://client.labox.eco.evil.test','https://evil.test','https://a:b@client.labox.eco','https://client.labox.eco/path']:
   with self.subTest(origin=value),self.assertRaises(ExportRejected):FixedTransport(value,lambda:'fixture')
 def test_redirect_denied(self):
  with self.assertRaisesRegex(ExportRejected,'REDIRECT_REFUSED'):NoRedirect().redirect_request(None,None,302,'Found',{},'https://evil.test')
 def test_paths_cannot_issue_native_restore_or_commands(self):
  transport=SupervisorBackupTransport(lambda:'fixture')
  for method,path in [('POST','/backups/foo/restore'),('DELETE','/backups/foo'),('GET','/backups/config/info'),('POST','/host/reboot')]:
   with self.subTest(path=path),self.assertRaisesRegex(ExportRejected,'INVALID_SUPERVISOR_OPERATION'):transport._open(method,path)
 def test_portal_paths_cannot_escape_allowlist(self):
  transport=FixedTransport('https://client.labox.eco',lambda:'fixture')
  for path in ['/api/device/backup-exports/../delete','/api/user','https://evil.test','/api/device/backup-exports/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?token=bad']:
   with self.subTest(path=path),self.assertRaisesRegex(ExportRejected,'INVALID_NATIVE_PATH'):transport._request('GET',path)
if __name__=='__main__':unittest.main()
