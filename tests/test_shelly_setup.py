import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from shelly_setup import configure
OWNER='a'*64;SESSION='123e4567-e89b-42d3-a456-426614174000';MAC='aabbccddeeff'
class Native:
 def __init__(self,domain='shelly',step='confirm_discovery',name='Shelly Plus 1'):
  self.domain=domain;self.step=step;self.name=name;self.native=[];self.posted=[];self.failure=False;self.entity_rows=[];self.device_rows=[];self.result='create_entry';self.source='zeroconf' if domain=='shelly' else 'bluetooth'
 def registry(self,command):
  if command['type']=='config_entries/flow/progress':return [{'flow_id':'flow1','handler':self.domain,'step_id':self.step,'context':{'source':self.source,'unique_id':MAC,'title_placeholders':{'name':self.name}}}]
  return {'config/device_registry/list':self.device_rows,'config/entity_registry/list':self.entity_rows,'config/area_registry/list':[]}[command['type']]
 def call(self,path,**kwargs):
  if path=='/config/config_entries/entry':return self.native
  if path=='/states':return [{'entity_id':r['entity_id'],'state':'on','attributes':{'friendly_name':'Contact','device_class':'door'}} for r in self.entity_rows]
  if path=='/config/config_entries/flow/flow1':
   fields=[{'name':'password'}] if self.step=='credentials' else [{'name':'bindkey'}] if self.step=='get_encryption_key' else []
   if kwargs.get('method')=='POST':
    self.posted.append(kwargs['payload'])
    if self.failure:raise TimeoutError('secret-password')
    if self.result=='form':return {'type':'form','step_id':self.step,'data_schema':fields,'errors':{'base':'invalid_auth'}}
    self.native=[{'entry_id':'entry1','domain':self.domain,'state':'loaded','disabled_by':None}]
    return {'type':'create_entry','result':{'entry_id':'entry1','data':{'password':'secret-password'}}}
   return {'flow_id':'flow1','handler':self.domain,'type':'form','step_id':self.step,'data_schema':fields}
  raise AssertionError('Unexpected endpoint '+path)
class ShellyTests(TestCase):
 def setUp(self):self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.data=Path(self.temp.name)
 def run_step(self,native,operation='status',**values):
  payload={'operation':operation,'ownerScope':OWNER}
  if operation!='status':payload|={'session':SESSION,'flowId':'flow1','mac':MAC}
  return configure(payload|values,native.call,registry=native.registry,data=self.data,clock=lambda:100)
 def test_status_is_read_only_and_native_discovery_excludes_cloud(self):
  native=Native();view=self.run_step(native);self.assertEqual(view['discoveries'][0]['mac'],MAC);self.assertEqual(native.posted,[]);self.assertFalse((self.data/'shelly-setup.json').exists())
 def test_user_created_and_bluetooth_wifi_provisioning_flows_are_not_claimed(self):
  for domain,source in [('shelly','user'),('shelly','bluetooth'),('bthome','user')]:
   n=Native(domain);n.source=source;self.assertEqual(self.run_step(n)['discoveries'],[])
 def test_unknown_bthome_device_is_not_presented_as_shelly(self):self.assertEqual(self.run_step(Native('bthome','bluetooth_confirm','Other brand'))['discoveries'],[])
 def test_confirm_binds_native_mac_and_never_calls_a_relay_service(self):
  n=Native();view=self.run_step(n,'connect',confirmed=True);self.assertEqual(n.posted,[{}]);self.assertEqual(view['entries'][0]['entryId'],'entry1');self.assertNotIn('secret-password',json.dumps(view))
 def test_mac_change_or_unconfirmed_selection_cannot_post(self):
  n=Native()
  for values in ({'mac':'112233445566','confirmed':True},{'confirmed':False}):
   with self.assertRaises((ValueError,RuntimeError)):self.run_step(n,'connect',**values)
  self.assertFalse(n.posted)
 def test_local_password_never_persisted_and_retry_is_sanitized(self):
  n=Native(step='credentials');view=self.run_step(n,'connect',confirmed=True);self.assertEqual(view['authentication']['kind'],'password');self.assertFalse(n.posted)
  n.result='form';view=self.run_step(n,'credentials',username='',password='secret-password');self.assertTrue(view['authentication']['retry']);self.assertNotIn('secret-password',(self.data/'shelly-setup.json').read_text());self.assertNotIn('secret-password',json.dumps(view))
 def test_foreign_owner_or_session_cannot_complete_password_step(self):
  n=Native(step='credentials');self.run_step(n,'connect',confirmed=True)
  for values in ({'ownerScope':'b'*64},{'session':'223e4567-e89b-42d3-a456-426614174000'}):
   with self.assertRaises(RuntimeError):self.run_step(n,'credentials',username='',password='secret-password',**values)
  self.assertFalse(n.posted)
 def test_unknown_submit_is_not_replayed(self):
  n=Native();n.failure=True
  with self.assertRaises(TimeoutError):self.run_step(n,'connect',confirmed=True)
  with self.assertRaises(RuntimeError):self.run_step(n,'connect',confirmed=True)
  self.assertEqual(len(n.posted),1)
 def test_shelly_blu_encryption_uses_native_key_field_only(self):
  n=Native('bthome','get_encryption_key','SBDW-002C test');self.assertEqual(self.run_step(n,'connect',confirmed=True)['authentication']['kind'],'key')
  view=self.run_step(n,'key',bindkey='c'*32);self.assertEqual(n.posted,[{'bindkey':'c'*32}]);self.assertNotIn('c'*32,(self.data/'shelly-setup.json').read_text());self.assertEqual(view['entries'][0]['domain'],'bthome')
 def test_native_devices_filter_platform_and_preserve_opening_sensor(self):
  n=Native('bthome','bluetooth_confirm','Shelly BLU DoorWindow');n.native=[{'entry_id':'entry1','domain':'bthome','state':'loaded','disabled_by':None}];n.device_rows=[{'id':'device1','config_entries':['entry1'],'manufacturer':'Shelly','model':'BLU DoorWindow','name':'Entrée','connections':[['bluetooth','aa:bb:cc:dd:ee:ff']]}];n.entity_rows=[{'device_id':'device1','config_entry_id':'entry1','platform':'bthome','entity_id':'binary_sensor.door'},{'device_id':'device1','config_entry_id':'foreign','platform':'tuya','entity_id':'switch.private'}]
  view=self.run_step(n);self.assertEqual(view['devices'][0]['mac'],MAC);self.assertEqual(view['devices'][0]['entities'][0]['deviceClass'],'door');self.assertNotIn('switch.private',json.dumps(view))
if __name__=='__main__':main()
