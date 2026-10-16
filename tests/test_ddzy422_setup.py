import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
import ddzy422_setup as setup

PAYLOAD={'host':'192.168.6.194','loggerSerial':2616442643,'mac':'d4:27:87:01:2c:d2'}
ADAPTERS=[{'enabled':True,'ipv4':[{'address':'192.168.6.180','network_prefix':24}]}]
class SetupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config';self.config.mkdir();self.data=self.root/'data'
  (self.config/'.storage').mkdir();self.storage=self.config/'.storage/core.config_entries';self.storage.write_text(json.dumps({'data':{'entries':[]}}))
 def install(self):return setup.install(self.config)
 def configure(self,call,payload=PAYLOAD):return setup.configure(payload,ADAPTERS,call,config=self.config,data=self.data)
 def test_atomic_component_install_then_preserve_idempotent(self):
  self.assertTrue(self.install()['restartRequired']);self.assertEqual(self.install()['status'],'existing_preserved')
  self.assertEqual(json.loads((self.config/'custom_components/labox_ddzy422/manifest.json').read_text())['requirements'],[])
  self.assertEqual(json.loads(self.storage.read_text()),{'data':{'entries':[]}})
 def test_known_legacy_bundle_upgrade_preserves_storage_and_retains_previous_files(self):
  from unittest.mock import patch
  import hashlib
  self.install();target=self.config/'custom_components/labox_ddzy422'
  (target/'const.py').write_text((target/'const.py').read_text().replace('POLL_SECONDS = 5','POLL_SECONDS = 30'))
  (target/'manifest.json').write_text((target/'manifest.json').read_text().replace('0.1.1','0.1.0'))
  before=self.storage.read_bytes();legacy=setup.LEGACY_INDEX.read_bytes()
  self.assertEqual(hashlib.sha256(legacy).hexdigest(),setup.LEGACY_INDEX_SHA256)
  result=self.install();self.assertEqual(result['version'],'0.1.1');self.assertIn('POLL_SECONDS = 5',(target/'const.py').read_text())
  previous=target.parent/'.123home-ddzy422-previous-010';self.assertIn('POLL_SECONDS = 30',(previous/'const.py').read_text());self.assertEqual(self.storage.read_bytes(),before)
  self.assertEqual(self.install()['status'],'existing_preserved')
 def test_legacy_with_foreign_file_is_not_replaced(self):
  self.install();target=self.config/'custom_components/labox_ddzy422'
  (target/'const.py').write_text((target/'const.py').read_text().replace('POLL_SECONDS = 5','POLL_SECONDS = 30'))
  (target/'manifest.json').write_text((target/'manifest.json').read_text().replace('0.1.1','0.1.0'))
  (target/'foreign.py').write_text('preserve')
  with self.assertRaisesRegex(RuntimeError,'conservée'):self.install()
  self.assertIn('POLL_SECONDS = 30',(target/'const.py').read_text())
 def test_foreign_component_and_symlink_are_preserved(self):
  self.install();target=self.config/'custom_components/labox_ddzy422/sensor.py';target.write_text('foreign')
  with self.assertRaisesRegex(RuntimeError,'conservée'):self.install()
  self.assertEqual(target.read_text(),'foreign')
  target.unlink();target.symlink_to(self.storage)
  with self.assertRaises(RuntimeError):self.install()
  self.assertTrue(target.is_symlink())
 def test_component_parent_symlink_is_refused(self):
  foreign=self.root/'foreign';foreign.mkdir();(self.config/'custom_components').symlink_to(foreign)
  with self.assertRaises(RuntimeError):self.install()
  self.assertEqual(list(foreign.iterdir()),[])
 def test_altered_bundle_refused_before_component_install(self):
  bundle=self.root/'bundle';shutil.copytree(setup.BUNDLE,bundle);(bundle/'sensor.py').write_text('altered')
  with self.assertRaises(RuntimeError):setup.install(self.config,bundle=bundle)
  self.assertFalse((self.config/'custom_components/labox_ddzy422').exists())
 def test_configflow_is_used_no_raw_storage_writes(self):
  self.install();before=self.storage.read_bytes()
  call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'f1'},{'type':'create_entry','result':{'entry_id':'e1'}}])
  result=self.configure(call);self.assertEqual(result['entryId'],'e1');self.assertEqual(self.storage.read_bytes(),before)
  self.assertEqual(call.call_args_list[1].kwargs['payload']['handler'],'labox_ddzy422');self.assertEqual(call.call_args_list[2].kwargs['payload']['logger_serial'],2616442643)
 def test_invalid_targets_and_identity_never_call_ha(self):
  self.install()
  for change in [{'host':'8.8.8.8'},{'host':'192.168.6.255'},{'host':'192.168.6.180'},{'mac':'FF:FF:FF:FF:FF:FF'},{'loggerSerial':True}]:
   call=Mock()
   with self.subTest(change=change),self.assertRaises(ValueError):self.configure(call,PAYLOAD|change)
   call.assert_not_called()
 def test_lost_response_never_creates_new_flow(self):
  self.install();call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'f1'},TimeoutError()])
  with self.assertRaises(TimeoutError):self.configure(call)
  retry=Mock(side_effect=[[],TimeoutError()])
  with self.assertRaises(TimeoutError):self.configure(retry)
  self.assertEqual(retry.call_count,2);self.assertTrue(all(c.kwargs.get('method','GET')=='GET' for c in retry.call_args_list))
 def test_completed_reset_allows_explicit_new_flow_for_exact_removed_entry(self):
  self.install();self.data.mkdir();values={'host':PAYLOAD['host'],'logger_serial':PAYLOAD['loggerSerial'],'mac':'D42787012CD2'}
  (self.data/f"ddzy422-{PAYLOAD['loggerSerial']}.json").write_text(json.dumps({'settings':values,'submitted':True,'flowId':'old','entryId':'removed'}))
  (self.data/'installation-reset.json').write_text(json.dumps({'state':'completed','removedEntryIds':['removed']}))
  call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'new'},{'type':'create_entry','result':{'entry_id':'new_entry'}}])
  self.assertEqual(self.configure(call)['entryId'],'new_entry');self.assertEqual(call.call_args_list[1].kwargs['method'],'POST')
 def test_matching_connection_reused_without_duplicate_or_poll(self):
  self.install();values={'host':PAYLOAD['host'],'logger_serial':PAYLOAD['loggerSerial'],'mac':'D42787012CD2'}
  self.storage.write_text(json.dumps({'data':{'entries':[{'domain':'labox_ddzy422','entry_id':'existing','unique_id':str(PAYLOAD['loggerSerial']),'data':values}]}}))
  call=Mock(return_value=[{'entry_id':'existing','state':'loaded'}]);self.assertEqual(self.configure(call)['entryId'],'existing');self.assertEqual(call.call_count,1)

if __name__=='__main__':unittest.main()
