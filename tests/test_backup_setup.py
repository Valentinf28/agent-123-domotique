import unittest
import tempfile
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent_123_domotique'))
from backup_setup import configure, fetch_configuration


class BackupSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / '.storage').mkdir()
        self.identifier = 'installation_' + 'a' * 32
        self.values = {'url':'https://home.123panneaux-solaires.fr/backups', 'username':self.identifier,
                       'password':'private-secret' * 4, 'verify_ssl':True, 'backup_path':'/'}
        self.configuration = {'state':'ready', 'remoteBackupAllowed':True,
                              'installationId':self.identifier, 'destination':self.values}
        self.stored([])
    def tearDown(self):
        self.temp.cleanup()
    def stored(self, entries):
        (self.root / '.storage/core.config_entries').write_text(json.dumps({'data':{'entries':entries}}))
    def run_setup(self, call):
        return configure(self.configuration, call, config=self.root, data=self.root/'data')
    def test_fetch_does_not_follow_redirects_or_send_token_to_http(self):
        with patch('backup_setup.urllib.request.build_opener') as opener:
            for url in ['http://portal.example/api','https://user:password@portal.example/api','https://portal.example/api?token=x']:
                with self.assertRaises(RuntimeError): fetch_configuration(url,'private-token')
            opener.assert_not_called()
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=b'{"state":"inactive"}'
            self.assertEqual(fetch_configuration('https://portal.example/api','private-token'),{'state':'inactive'})
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://portal.example/api/agent/backup-configuration')
            self.assertEqual(request.get_header('Authorization'),'Bearer private-token')
            handler=opener.call_args.args[0]()
            with self.assertRaises(RuntimeError): handler.redirect_request(None,None,302,'Found',{},'https://other.example')

    def test_create_then_readback_preserves_existing_destination_and_key(self):
        other = {'domain':'webdav','entry_id':'other','data':{'username':'other'}}
        self.stored([other])
        call=Mock(side_effect=[[{'entry_id':'other','state':'loaded'}],
            {'type':'form','step_id':'user','flow_id':'flow1'}, {'type':'create_entry'}])
        self.assertEqual(self.run_setup(call)['state'], 'destination_pending')
        journal=(self.root/'data/backup-setup.json').read_text()
        self.assertNotIn(self.values['password'],journal)
        self.assertEqual(call.call_args.kwargs['payload'],self.values)
        own={'domain':'webdav','entry_id':'mine','data':self.values}
        self.stored([other,own])
        call=Mock(return_value=[{'entry_id':'other','state':'loaded'},{'entry_id':'mine','state':'loaded'}])
        self.assertEqual(self.run_setup(call),{'state':'destination_ready','entryId':'mine','backupVerified':False})
        self.assertEqual(call.call_count,1)
        self.assertEqual(json.loads((self.root/'.storage/core.config_entries').read_text())['data']['entries'],[other,own])
    def test_lost_submission_never_starts_second_flow(self):
        call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'flow1'},TimeoutError()])
        with self.assertRaises(TimeoutError): self.run_setup(call)
        call=Mock(side_effect=[[],RuntimeError('flow not found')])
        with self.assertRaises(RuntimeError): self.run_setup(call)
        self.assertEqual(call.call_args.args[0],'/config/config_entries/flow/flow1')
        self.assertEqual(call.call_count,2)
    def test_wrong_installation_or_unencrypted_destination_rejected_before_calls(self):
        for key,value in [('username','another'),('verify_ssl',False),('url','http://unsafe')]:
            original=self.values[key];self.values[key]=value
            call=Mock()
            with self.assertRaises(RuntimeError): self.run_setup(call)
            call.assert_not_called();self.values[key]=original
    def test_changed_existing_password_is_not_overwritten(self):
        self.stored([{'domain':'webdav','entry_id':'mine','data':{**self.values,'password':'other'}}])
        call=Mock(return_value=[{'entry_id':'mine','state':'loaded'}])
        with self.assertRaisesRegex(RuntimeError,'conservée'): self.run_setup(call)
        self.assertEqual(call.call_count,1)

if __name__=='__main__': unittest.main()
