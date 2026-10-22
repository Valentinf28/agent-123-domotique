from pathlib import Path
import sys
import tempfile
import json
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from tuya_setup import configure
OWNER='a'*64
SESSION='123e4567-e89b-42d3-a456-426614174000'
ENTRY={'domain':'tuya','entry_id':'tuya1','state':'loaded','disabled_by':None}
USER={'type':'form','handler':'tuya','flow_id':'flow1','step_id':'user','data_schema':[]}
SCAN={'type':'form','handler':'tuya','flow_id':'flow1','step_id':'scan','data_schema':[{'name':'QR','selector':{'qr_code':{'data':'tuyaSmart--qrLogin?token=temporary-code'}}}]}
class TuyaSetupTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.data=Path(self.directory.name)
 def run_step(self,operation,call,**kw):return configure({'operation':operation,'ownerScope':OWNER,'session':SESSION,**kw},call,data=self.data,now=100)
 def start(self):return self.run_step('start',Mock(side_effect=[[],USER]))
 def test_native_start_does_not_install_anything_or_collect_password(self):
  call=Mock(side_effect=[[],USER]);result=self.run_step('start',call);self.assertEqual(result['status'],'user_code')
  self.assertEqual(call.call_args.kwargs['payload'],{'handler':'tuya','show_advanced_options':False})
  self.assertEqual((self.data/'tuya-flow.json').stat().st_mode&0o777,0o600)
 def test_existing_integration_preserved_and_no_duplicate_flow(self):
  call=Mock(return_value=[ENTRY]);result=self.run_step('start',call);self.assertEqual(result['status'],'existing');self.assertEqual(call.call_count,1)
 def test_user_code_only_sent_to_native_flow_and_never_persisted(self):
  self.start();call=Mock(side_effect=[[],USER,SCAN]);result=self.run_step('code',call,userCode='MyUserCode');self.assertEqual(result['status'],'scan')
  self.assertEqual(call.call_args.kwargs['payload'],{'user_code':'MyUserCode'})
  self.assertNotIn('MyUserCode',(self.data/'tuya-flow.json').read_text());self.assertNotIn('temporary-code',(self.data/'tuya-flow.json').read_text())
 def test_create_entry_response_strips_all_tokens_and_does_not_verify_devices(self):
  self.start();raw={'type':'create_entry','result':{'entry_id':'tuya1','data':{'access_token':'never-expose'}}}
  result=self.run_step('confirm',Mock(side_effect=[[],SCAN,raw,[ENTRY]]));self.assertEqual(result['status'],'configured');self.assertFalse(result['devicesVerified']);self.assertNotIn('never-expose',json.dumps(result))
 def test_unconfirmed_creation_never_reports_success(self):
  self.start();raw={'type':'create_entry','result':{'entry_id':'tuya1'}}
  with self.assertRaisesRegex(RuntimeError,'confirmée'):self.run_step('confirm',Mock(side_effect=[[],SCAN,raw,[]]))
 def test_different_owner_or_session_cannot_resume_or_cancel(self):
  self.start()
  for values in ({'ownerScope':'b'*64},{'session':'223e4567-e89b-42d3-a456-426614174000'}):
   for operation in ('start','code','confirm','cancel'):
    with self.subTest(values=values,operation=operation),self.assertRaisesRegex(RuntimeError,'autre session'):
     self.run_step(operation,Mock(return_value=[]),**values)
 def test_lost_start_response_cannot_start_duplicate_or_erase_unknown_flow(self):
  with self.assertRaises(TimeoutError):self.run_step('start',Mock(side_effect=[[],TimeoutError()]))
  for operation in ('start','cancel'):
   call=Mock(return_value=[])
   with self.assertRaisesRegex(RuntimeError,'démarrage'):self.run_step(operation,call)
   self.assertEqual(call.call_count,1)
 def test_expired_abandoned_flow_is_cancelled_before_new_session_starts(self):
  self.start();call=Mock(side_effect=[[],{},USER|{'flow_id':'newflow'}])
  result=configure({'operation':'start','ownerScope':'b'*64,'session':'223e4567-e89b-42d3-a456-426614174000'},call,data=self.data,now=701)
  self.assertEqual(result['status'],'user_code');self.assertEqual(call.call_args_list[1].kwargs,{'method':'DELETE'})
  self.assertEqual(json.loads((self.data/'tuya-flow.json').read_text())['ownerScope'],'b'*64)
 def test_expired_lost_initial_start_can_be_replaced_without_replaying_user_code(self):
  with self.assertRaises(TimeoutError):self.run_step('start',Mock(side_effect=[[],TimeoutError()]))
  call=Mock(side_effect=[[],USER])
  self.assertEqual(configure({'operation':'start','ownerScope':OWNER,'session':SESSION},call,data=self.data,now=701)['status'],'user_code')
  self.assertEqual(call.call_count,2)
 def test_cancel_deletes_only_own_recorded_flow(self):
  self.start();call=Mock(side_effect=[[],{}]);self.assertEqual(self.run_step('cancel',call)['status'],'cancelled');self.assertEqual(call.call_args.args,('/config/config_entries/flow/flow1',));self.assertEqual(call.call_args.kwargs,{'method':'DELETE'})
 def test_expired_session_never_confirms(self):
  self.start();call=Mock(return_value=[])
  with self.assertRaisesRegex(RuntimeError,'écoulé'):configure({'operation':'confirm','ownerScope':OWNER,'session':SESSION},call,data=self.data,now=701)
  self.assertEqual(call.call_count,1)
 def test_reload_cannot_target_other_integration_or_disabled_entry(self):
  for entries in ([ENTRY],[ENTRY|{'disabled_by':'user'}]):
   call=Mock(return_value=entries)
   with self.assertRaises(ValueError):self.run_step('reload',call,entryId='foreign')
   self.assertEqual(call.call_count,1)
 def test_inventory_names_filtered_to_native_tuya_entries_without_secrets(self):
  entities=[{'config_entry_id':'tuya1','platform':'tuya','entity_id':'switch.tongou','device_id':'dev1'},{'config_entry_id':'foreign','platform':'tuya','entity_id':'switch.private','device_id':'dev2'},{'config_entry_id':'tuya1','platform':'tuya','entity_id':'lock.front','device_id':'dev1'}]
  registry=Mock(side_effect=[entities,[{'id':'dev1','name_by_user':'Ballon','manufacturer':'Tongou','model':'exact','area_id':'area1'}],[{'area_id':'area1','name':'Garage'}]])
  call=Mock(side_effect=[[ENTRY],[{'entity_id':'switch.tongou','state':'on','attributes':{'friendly_name':'Ballon','secret':'never-expose'}}]])
  result=configure({'operation':'status','ownerScope':OWNER},call,data=self.data,now=100,registry=registry)
  self.assertEqual(result['devices'][0]['name'],'Ballon');self.assertEqual(result['devices'][0]['room'],'Garage');self.assertNotIn('never-expose',json.dumps(result));self.assertNotIn('switch.private',json.dumps(result));self.assertNotIn('lock.front',json.dumps(result))
 def test_wrong_handler_and_hostile_qr_are_refused(self):
  for flow in (USER|{'handler':'evil'},SCAN|{'data_schema':[{'name':'QR','selector':{'qr_code':{'data':'https://evil.example'}}}]}):
   with self.assertRaises(RuntimeError):self.run_step('start',Mock(side_effect=[[],flow]))
   (self.data/'tuya-flow.json').unlink(missing_ok=True)
if __name__=='__main__':unittest.main()
