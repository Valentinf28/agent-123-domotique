import copy
import json
from pathlib import Path
import tempfile
import unittest
from automation_edit import update, read, digest

class AutomationEditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
  self.entity='automation.ma_maison_filtration';self.config={'id':'ma_maison_123456_abcdef','alias':'1.2.3 Home · Filtration','description':'Créée depuis le portail Ma Maison','trigger':[{'platform':'time','at':'17:06:00'}],'condition':[],'action':[{'service':'switch.turn_on','target':{'entity_id':'switch.filtration'}}],'mode':'single'}
  self.initial=copy.deepcopy(self.config);self.writes=[];self.reloads=0;self.fail_reload=False;self.active='off';self.concurrent=False;self.reads=0;self.flip_enabled=False;self.enable_calls=[]
  self.payload={'entityId':self.entity,'name':'Filtration matin','triggerType':'time','time':'08:30','weekdays':['mon','fri'],'targetEntityId':'switch.filtration','domain':'switch','service':'turn_on','expectedDigest':digest(self.initial)}
 def ws(self,payload):
  self.assertEqual(payload,{'type':'automation/config','entity_id':self.entity})
  return {'success':True,'result':{'config':copy.deepcopy(self.config)}}
 def call(self,path,method='GET',payload=None):
  if path=='/states/'+self.entity:return {'entity_id':self.entity,'state':self.active}
  if path=='/states/switch.filtration':return {'entity_id':'switch.filtration','state':'off'}
  if path in ('/services/automation/turn_on','/services/automation/turn_off'):
   self.assertEqual(payload,{'entity_id':self.entity});self.enable_calls.append(path);self.active='on' if path.endswith('turn_on') else 'off';return []
  if path=='/services/automation/reload':
   self.reloads+=1
   if self.flip_enabled:self.active='on'
   if self.fail_reload and self.reloads==1:raise TimeoutError('simulated transport failure')
   return []
  self.assertEqual(path,'/config/automation/config/ma_maison_123456_abcdef')
  if method=='GET':
   self.reads+=1
   if self.concurrent and self.reads==2:self.config['alias']='1.2.3 Home · Concurrent'
   return copy.deepcopy(self.config)
  self.assertEqual(method,'POST');self.writes.append(copy.deepcopy(payload));self.config=copy.deepcopy(payload);return {}
 def execute(self,payload=None,identifier='operation-1'):
  return update(payload or self.payload,self.call,self.ws,operation_id=identifier,data=self.data)
 def test_edit_keeps_native_id_disabled_state_and_returns_real_entity(self):
  result=self.execute();self.assertEqual(result['entityId'],self.entity);self.assertTrue(result['updated']);self.assertEqual(self.config['id'],self.initial['id']);self.assertEqual(self.active,'off');self.assertEqual(self.config['trigger'],[{'platform':'time','at':'08:30:00'}]);self.assertEqual(self.config['condition'],[{'condition':'time','weekday':['mon','fri']}]);self.assertEqual(len(self.writes),1)
  saved=next((self.data/'automation-edits').glob('*.json'));self.assertEqual(saved.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(saved.read_text())['original'],self.initial)
 def test_sunrise_and_all_days_are_represented_explicitly(self):
  self.execute(self.payload|{'triggerType':'sunrise','time':None,'weekdays':[]});self.assertEqual(self.config['trigger'],[{'platform':'sun','event':'sunrise'}]);self.assertEqual(self.config['condition'],[])
 def test_verified_duplicate_returns_result_without_reloading(self):
  first=self.execute();second=self.execute();self.assertEqual(first,second);self.assertEqual(len(self.writes),1);self.assertEqual(self.reloads,1)
 def test_reused_command_identity_with_different_payload_is_rejected(self):
  self.execute()
  with self.assertRaises(ValueError):self.execute(self.payload|{'time':'09:00'})
  self.assertEqual(len(self.writes),1)
 def test_native_provenance_and_complex_rules_fail_before_write(self):
  variants=[{'id':'user_rule'}, {'description':'elsewhere'}, {'alias':'other'}, {'trigger':[{'platform':'state','entity_id':'binary_sensor.x'}]}, {'action':self.initial['action']*2}, {'variables':{'x':1}}, {'condition':[{'condition':'template','value_template':'{{ true }}'}]}]
  for change in variants:
   with self.subTest(change=change):
    self.config=self.initial|change
    with self.assertRaises(ValueError):self.execute()
    self.assertEqual(self.writes,[])
 def test_invalid_targets_and_unrepresentable_inputs_fail_before_write(self):
  for change in [{'time':'25:00'}, {'weekdays':['mon','mon']}, {'weekdays':['monday']}, {'triggerType':'sunset','time':'08:30'}, {'targetEntityId':'script.run','domain':'script','service':'turn_on'}, {'targetEntityId':'switch.a/../b'}]:
   with self.subTest(change=change):
    with self.assertRaises(ValueError):self.execute(self.payload|change)
    self.assertEqual(self.writes,[])
 def test_reload_failure_restores_previous_file_without_triggering_actions(self):
  self.fail_reload=True
  with self.assertRaisesRegex(RuntimeError,'Configuration précédente conservée'):self.execute()
  self.assertEqual(self.config,self.initial);self.assertEqual(len(self.writes),2);self.assertEqual(self.active,'off')
  with self.assertRaisesRegex(RuntimeError,'aucun nouvel envoi'):self.execute()
  self.assertEqual(len(self.writes),2)
 def test_concurrent_native_edit_never_overwritten(self):
  self.concurrent=True
  with self.assertRaisesRegex(RuntimeError,'concurrente'):self.execute()
  self.assertEqual(self.writes,[]);self.assertEqual(self.config['alias'],'1.2.3 Home · Concurrent')
 def test_reload_state_flip_restores_original_disabled_state(self):
  self.flip_enabled=True
  with self.assertRaises(RuntimeError):self.execute()
  self.assertEqual(self.config,self.initial);self.assertEqual(self.active,'off');self.assertEqual(self.enable_calls,['/services/automation/turn_off'])
 def test_dotted_brand_prefix_supported_with_same_provenance(self):
  self.config['alias']='1.2.3. Home · Filtration';self.payload['expectedDigest']=digest(self.config);self.execute();self.assertEqual(len(self.writes),1)

 def test_read_normalizes_actual_config_without_journal_or_writes(self):
  result=read({'entityId':self.entity},self.call,self.ws)
  self.assertEqual(result['name'],'Filtration');self.assertEqual(result['time'],'17:06');self.assertFalse(result['enabled']);self.assertEqual(result['configDigest'],digest(self.initial));self.assertEqual(self.writes,[]);self.assertEqual(list(self.data.iterdir()),[])
 def test_changed_since_ui_read_rejected_before_write(self):
  self.config['alias']='1.2.3 Home · External change'
  with self.assertRaisesRegex(RuntimeError,'depuis sa lecture'):self.execute()
  self.assertEqual(self.writes,[])


class AutomationDeleteTests(unittest.TestCase):
 setUp=AutomationEditTests.setUp
 ws=AutomationEditTests.ws
 def call(self,path,method='GET',payload=None):
  import urllib.error
  if path.startswith('/config/automation/config/'):
   if method=='DELETE':self.writes.append('DELETE');self.config=None;return {}
   if method=='GET' and self.config is None:raise urllib.error.HTTPError(path,404,'missing',{},None)
  return AutomationEditTests.call(self,path,method,payload)
 def execute_delete(self,payload=None):
  from automation_edit import delete,digest
  return delete(payload or {'entityId':self.entity,'expectedDigest':digest(self.initial)},self.call,self.ws,operation_id='delete-1',data=self.data)
 def test_delete_confirms_file_absence_and_does_not_repeat(self):
  first=self.execute_delete();self.assertTrue(first['deleted']);self.assertIsNone(self.config);self.assertEqual(self.execute_delete(),first);self.assertEqual(self.writes,['DELETE'])
 def test_delete_requires_fresh_digest_and_never_accepts_legacy_payload(self):
  with self.assertRaises(ValueError):self.execute_delete({'entityId':self.entity})
  with self.assertRaises(RuntimeError):self.execute_delete({'entityId':self.entity,'expectedDigest':'bad'})
  self.assertEqual(self.writes,[])
 def test_uncertain_delete_reload_restores_disabled_state(self):
  self.fail_reload=True;self.flip_enabled=True
  with self.assertRaises(RuntimeError):self.execute_delete()
  self.assertEqual(self.config,self.initial);self.assertEqual(self.active,'off');self.assertEqual(self.enable_calls,['/services/automation/turn_off'])
  journal=json.loads(next((self.data/'automation-edits').glob('*.json')).read_text());self.assertEqual(journal['enabledState'],'off')
 def test_delete_reload_failure_restores_native_configuration(self):
  self.fail_reload=True
  with self.assertRaisesRegex(RuntimeError,'Configuration précédente conservée'):self.execute_delete()
  self.assertEqual(self.config,self.initial);self.assertEqual(self.active,'off')

class ActualNativeAdapterTests(AutomationEditTests):
 def ws(self,payload):return super().ws(payload)['result']
 def test_real_adapter_read_and_edit(self):
  self.assertEqual(read({'entityId':self.entity},self.call,self.ws)['configDigest'],digest(self.initial))
  self.assertTrue(self.execute()['updated'])
 def test_failed_or_ambiguous_envelope_cannot_enable_mutation(self):
  from automation_edit import native_config
  for value in [None, [], {}, {'success':False,'result':{'config':self.initial}}, {'config':self.initial,'error':'denied'}, {'result':{'config':self.initial}}, {'success':True,'result':None}, {'config':None}]:
   with self.subTest(value=value):
    with self.assertRaises(ValueError):native_config(lambda _:value,self.entity)
  self.assertEqual(self.writes,[])

class ActualNativeDeleteTests(AutomationDeleteTests):
 def ws(self,payload):return AutomationEditTests.ws(self,payload)['result']

if __name__=='__main__':unittest.main()
