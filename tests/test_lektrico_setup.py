import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from lektrico_setup import configure
from ev_discovery import discover

OWNER='a'*64
class NativeHA:
 def __init__(self):self.configured=False;self.lost=False;self.posts=[];self.extra_entries=[];self.foreign=False
 def call(self,path,**kwargs):
  if path.startswith('/config/config_entries/entry'):
   return ([{'domain':'lektrico','entry_id':'entry1','state':'loaded'}] if self.configured else [])+self.extra_entries
  if path=='/states':return [{'entity_id':'sensor.real_power','state':'0','attributes':{'unit_of_measurement':'W','private_token':'PRIVATE'}}]
  if path=='/config/config_entries/flow/flow1':
   if kwargs.get('method')=='POST':
    self.posts.append((path,kwargs));self.configured=True
    if self.lost:raise TimeoutError('response lost')
    return {'type':'create_entry'}
   return {'type':'form','handler':'lektrico','step_id':'confirm'}
  raise AssertionError('Unexpected endpoint '+path)
 def registry(self,command):
  if command['type']=='config_entries/flow/progress':return [] if self.configured else [{'flow_id':'flow1','handler':'lektrico' if not self.foreign else 'other','step_id':'confirm','context':{'source':'zeroconf','title_placeholders':{'serial_number':'1234','name':'Lektrico_1234'},'private':'PRIVATE'}}]
  if command['type']=='config/device_registry/list':return [{'id':'device1','config_entries':['entry1'],'identifiers':[['lektrico','1234']],'name':'Borne','manufacturer':'Lektrico','model':'1P7K'}]
  if command['type']=='config/entity_registry/list':return [{'entity_id':'sensor.real_power','device_id':'device1','config_entry_id':'entry1','platform':'lektrico'}]
  raise AssertionError(command)
class LektricoTests(unittest.TestCase):
 def payload(self,**change):return {'operation':'confirm','ownerScope':OWNER,'flowId':'flow1','serial':'1234','identityConfirmed':True,**change}
 def test_discovery_does_not_probe_or_configure(self):
  ha=NativeHA();view=discover({'operation':'status','ownerScope':OWNER},ha.call,registry=ha.registry)
  self.assertEqual(view['discoveries'][0]['adapter'],'lektrico');self.assertEqual(ha.posts,[]);self.assertNotIn('PRIVATE',str(view))
 def test_confirm_reuses_native_identity_and_actual_registry(self):
  ha=NativeHA();view=configure(self.payload(),ha.call,registry=ha.registry)
  self.assertEqual(view['devices'][0]['serial'],'1234');self.assertEqual(view['devices'][0]['entities'][0]['state'],'0')
  configure(self.payload(),ha.call,registry=ha.registry);self.assertEqual(len(ha.posts),1)
  self.assertNotIn('PRIVATE',str(view));self.assertFalse(view['devicesVerified'])
 def test_lost_confirmation_response_recovers_existing_identity(self):
  ha=NativeHA();ha.lost=True
  with self.assertRaises(TimeoutError):configure(self.payload(),ha.call,registry=ha.registry)
  view=configure(self.payload(),ha.call,registry=ha.registry)
  self.assertEqual(view['status'],'existing');self.assertEqual(len(ha.posts),1)
 def test_wrong_serial_expired_flow_foreign_handler_and_missing_confirmation_refused(self):
  for change in ({'serial':'999'},{'flowId':'expired'},{'identityConfirmed':False},{'host':'http://evil'}):
   ha=NativeHA()
   with self.assertRaises((ValueError,RuntimeError)):configure(self.payload(**change),ha.call,registry=ha.registry)
   self.assertEqual(ha.posts,[])
  ha=NativeHA();ha.foreign=True
  with self.assertRaises(ValueError):configure(self.payload(),ha.call,registry=ha.registry)
 def test_discovery_rejects_arbitrary_targets(self):
  ha=NativeHA()
  with self.assertRaises(ValueError):discover({'operation':'status','ownerScope':OWNER,'url':'http://evil'},ha.call,registry=ha.registry)
 def test_existing_other_family_keeps_its_origin_and_fallback_neutral(self):
  ha=NativeHA();ha.extra_entries=[{'domain':'wallbox','entry_id':'wallentry','state':'loaded'},{'domain':'easee','entry_id':'easeentry','state':'loaded'}]
  original=ha.registry
  def registry(command):
   if command['type']=='config/device_registry/list':return [{'id':'wall','config_entries':['wallentry']},{'id':'ease','config_entries':['easeentry']}]
   if command['type']=='config/entity_registry/list':return [{'entity_id':'sensor.real_power','device_id':'wall','config_entry_id':'wallentry','platform':'wallbox'}]
   return original(command)
  view=discover({'operation':'status','ownerScope':OWNER},ha.call,registry=registry)
  self.assertEqual({e['domain'] for e in view['entries']},{'wallbox','easee'})
  wall=next(device for device in view['devices'] if device['domain']=='wallbox');self.assertEqual(wall['brand'],'wallbox');self.assertNotEqual(wall['name'],'Lektrico')
 def test_legacy_keba_registry_read_without_fabricating_entry(self):
  ha=NativeHA();original=ha.registry
  def registry(command):
   if command['type']=='config/device_registry/list':return [{'id':'keba1','config_entries':[],'manufacturer':'KEBA'}]
   if command['type']=='config/entity_registry/list':return [{'entity_id':'sensor.real_power','device_id':'keba1','config_entry_id':None,'platform':'keba'}]
   return original(command)
  view=discover({'operation':'status','ownerScope':OWNER},ha.call,registry=registry)
  self.assertEqual(view['entries'],[]);self.assertEqual(view['devices'][0]['domain'],'keba');self.assertEqual(view['status'],'existing')
if __name__=='__main__':unittest.main()
