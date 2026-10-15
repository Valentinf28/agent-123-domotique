import sys,unittest,tempfile,json,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from equipment_setup import configure,discovered,form_view,device_list
OWNER='a'*64;SESSION=str(uuid.uuid4())
class NativeFixture:
 def __init__(self,domain='hue',step='link',schema=None):
  self.domain=domain;self.step=step;self.schema=schema or [];self.calls=[];self.configured=[];self.reply=None
  sources={'hue':'zeroconf','wiz':'integration_discovery','tplink':'dhcp','switchbot':'bluetooth','reolink':'dhcp','enphase_envoy':'zeroconf'}
  self.flow={'flow_id':'native-flow','handler':domain,'step_id':step,'type':'form','data_schema':self.schema}
  self.progress=[{'flow_id':'native-flow','handler':domain,'step_id':step,'context':{'source':sources.get(domain,'user'),'unique_id':'unique-device','title_placeholders':{'name':'Fixture device'}}}]
 def call(self,path,**kwargs):
  self.calls.append((path,kwargs))
  if path=='/config/config_entries/entry':return self.configured
  if path=='/states':return []
  if path.startswith('/services/'):
   assert path=='/services/zha/permit';return []
  if path=='/config/config_entries/flow/native-flow':
   if kwargs.get('method')=='POST':
    if isinstance(self.reply,Exception):raise self.reply
    if self.reply:return self.reply
    self.configured=[{'entry_id':'created','domain':self.domain,'state':'loaded'}];self.progress=[]
    return {'type':'create_entry','result':{'entry_id':'created'}}
   return self.flow
  raise AssertionError(path)
 def registry(self,message):
  self.calls.append(('ws',message))
  if message['type']=='config_entries/flow/progress':return self.progress
  if message['type']=='matter/commission':return None
  return []
 def request(self,operation,**args):return {'operation':operation,'connector':self.domain,'ownerScope':OWNER,**args}
 def open(self,data):
  d=discovered(self.registry,self.domain)[0];return configure(self.request('open',session=SESSION,flowId=d['flowId'],fingerprint=d['fingerprint']),self.call,registry=self.registry,data=data)
 def submit(self,data,values={},cloud=False,**extra):
  d=discovered(self.registry,self.domain)[0];return configure(self.request('submit',session=SESSION,flowId=d['flowId'],fingerprint=d['fingerprint'],step=self.step,values=values,cloudConsent=cloud,**extra),self.call,registry=self.registry,data=data)
class EquipmentSetup(unittest.TestCase):
 def test_local_families_confirm_native_discovery_only(self):
  for domain,step in [('hue','link'),('wiz','discovery_confirm'),('tplink','discovery_confirm'),('switchbot','confirm')]:
   with self.subTest(domain=domain),tempfile.TemporaryDirectory() as d:
    f=NativeFixture(domain,step);view=f.open(Path(d));self.assertEqual(view['form']['kind'],'form');self.assertFalse(any(c[1].get('method')=='POST' for c in f.calls));result=f.submit(Path(d));self.assertEqual(result['entries'][0]['entryId'],'created')
 def test_no_user_or_reauth_flows_or_other_brands(self):
  f=NativeFixture();f.progress[0]['context']['source']='user';self.assertEqual(discovered(f.registry,'hue'),[])
  f.progress[0]['context']['source']='reauth';self.assertEqual(discovered(f.registry,'hue'),[])
  f=NativeFixture();self.assertEqual(discovered(f.registry,'wiz'),[])
 def test_credentials_never_returned_or_journalled(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture('reolink','user',[{'name':'username','required':True},{'name':'password','required':True}]);f.open(Path(d));f.reply={'type':'form','flow_id':'native-flow','handler':'reolink','step_id':'user','data_schema':f.schema,'errors':{'base':'secret-password'}}
   result=f.submit(Path(d),{'username':'admin','password':'secret-password'});self.assertTrue(result['form']['retry']);self.assertNotIn('secret-password',json.dumps(result));self.assertNotIn('secret-password',(Path(d)/'equipment-setup.json').read_text())
 def test_cloud_consent_and_extra_fields(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture('enphase_envoy','user',[{'name':'username','required':True},{'name':'password','required':True}]);f.open(Path(d));self.assertRaises(ValueError,f.submit,Path(d),{'username':'account','password':'secret'})
   self.assertRaises(ValueError,f.submit,Path(d),{'username':'account','password':'secret','host':'http://evil'},True)
   result=f.submit(Path(d),{'username':'account','password':'secret'},True);self.assertEqual(result['entries'][0]['domain'],'enphase_envoy')
 def test_foreign_session_or_unknown_submission_cannot_replay(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture();f.open(Path(d));candidate=discovered(f.registry,'hue')[0]
   self.assertRaises(RuntimeError,configure,f.request('submit',session=str(uuid.uuid4()),flowId=candidate['flowId'],fingerprint=candidate['fingerprint'],step='link',values={},cloudConsent=False),f.call,registry=f.registry,data=Path(d))
   f.reply=TimeoutError('lost');self.assertRaises(TimeoutError,f.submit,Path(d));self.assertRaises(RuntimeError,f.submit,Path(d));self.assertEqual(len([c for c in f.calls if c[1].get('method')=='POST']),1)
 def test_privacy_mode_is_never_disabled_and_unknown_schema_blocked(self):
  self.assertEqual(form_view({'type':'form','step_id':'privacy','data_schema':[]},'reolink')['kind'],'blocked')
  self.assertEqual(form_view({'type':'form','step_id':'link','data_schema':[{'name':'danger'}]},'hue')['kind'],'blocked')
 def test_zigbee_permit_is_exact_and_replay_safe(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture('zha');f.configured=[{'entry_id':'zha-native','domain':'zha','state':'loaded'}];payload=f.request('pair',session=SESSION,operationId=str(uuid.uuid4()),confirmed=True,code='',networkAlreadyConnected=False)
   configure(payload,f.call,registry=f.registry,data=Path(d));configure(payload,f.call,registry=f.registry,data=Path(d));calls=[c for c in f.calls if c[0]=='/services/zha/permit'];self.assertEqual(calls,[('/services/zha/permit',{'method':'POST','payload':{'duration':60}})])
   configure(f.request('close_pairing',session=SESSION),f.call,registry=f.registry,data=Path(d));self.assertEqual([c for c in f.calls if c[0]=='/services/zha/permit'][-1][1]['payload'],{'duration':0})
 def test_matter_network_only_code_not_stored_and_no_second_operation(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture('matter');f.configured=[{'entry_id':'matter-native','domain':'matter','state':'loaded'}];payload=f.request('pair',session=SESSION,operationId=str(uuid.uuid4()),confirmed=True,code='12345678901',networkAlreadyConnected=True)
   configure(payload,f.call,registry=f.registry,data=Path(d));self.assertNotIn('12345678901',(Path(d)/'equipment-setup.json').read_text());self.assertEqual([c[1] for c in f.calls if c[0]=='ws' and c[1]['type']=='matter/commission'],[{'type':'matter/commission','code':'12345678901','network_only':True}]);self.assertRaises(RuntimeError,configure,{**payload,'operationId':str(uuid.uuid4())},f.call,registry=f.registry,data=Path(d))
 def test_pairing_missing_radio_is_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   f=NativeFixture('zha');self.assertRaises(RuntimeError,configure,f.request('pair',session=SESSION,operationId=str(uuid.uuid4()),confirmed=True,code='',networkAlreadyConnected=False),f.call,registry=f.registry,data=Path(d))
 def test_generic_proxy_or_services_not_authorized(self):
  f=NativeFixture();self.assertRaises(ValueError,configure,{'operation':'status','connector':'hue','ownerScope':OWNER,'service':'switch.turn_on'},f.call,registry=f.registry)
if __name__=='__main__':unittest.main()
