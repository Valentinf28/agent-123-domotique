import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from equipment_setup import configure
from integration_flow import schema_fields,public_flow,validate_values,authorization_url

OWNER='a'*64

class Fixture:
 def __init__(self,domain='homekit_controller',schema=None):
  self.domain=domain;self.session=str(uuid.uuid4());self.calls=[];self.native=[];self.reply=None
  self.flow={'type':'form','handler':domain,'flow_id':'flow_fixture','step_id':'user','data_schema':schema or []}
 def call(self,path,**kw):
  self.calls.append((path,kw))
  if path=='/config':return {'version':'2026.10.1'}
  if path=='/config/config_entries/entry':return self.native
  if path=='/states':return []
  if path=='/config/config_entries/flow':return self.flow
  if path=='/config/config_entries/flow/flow_fixture':
   if kw.get('method')=='DELETE':return {}
   if kw.get('method')=='POST':
    if isinstance(self.reply,Exception):raise self.reply
    if self.reply is not None:self.flow=self.reply
   return self.flow
  raise AssertionError(path)
 def registry(self,message):return []
 def run(self,data,operation,**extra):
  payload={'operation':operation,'connector':self.domain,'ownerScope':OWNER,'session':self.session,**extra}
  return configure(payload,self.call,registry=self.registry,data=data)
 def start(self,data):return self.run(data,'flow_start',cloudConsent=True)
 def advance(self,data,values):return self.run(data,'flow_advance',flowId='flow_fixture',step=self.flow['step_id'],values=values,cloudConsent=True)

class NativeFlowTests(unittest.TestCase):
 def test_each_native_connector_can_start_its_own_ha_user_flow(self):
  from equipment_setup import DOMAINS
  for domain in DOMAINS:
   with self.subTest(domain=domain),tempfile.TemporaryDirectory()as directory:
    f=Fixture(domain);view=f.start(Path(directory));self.assertEqual(view['flow']['kind'],'form')
    writes=[x for x in f.calls if x[1].get('method')=='POST'];self.assertEqual(writes,[('/config/config_entries/flow',{'method':'POST','payload':{'handler':domain,'show_advanced_options':False}})])
 def test_homekit_code_and_smarthome_password_are_secret_and_never_journalled(self):
  for domain,name in [('homekit_controller','pairing_code'),('midea','password')]:
   with self.subTest(domain=domain),tempfile.TemporaryDirectory()as directory:
    f=Fixture(domain,[{'name':name,'required':True,'type':'string','default':'SECRET-NEVER-RETURN'}]);root=Path(directory)
    self.assertEqual(f.start(root)['flow']['fields'][0]['kind'],'secret')
    f.reply={**f.flow,'errors':{'base':'invalid_auth'}}
    view=f.advance(root,{name:'PRIVATE-CREDENTIAL'})
    self.assertTrue(view['flow']['retry']);self.assertNotIn('PRIVATE-CREDENTIAL',json.dumps(view));self.assertNotIn('SECRET-NEVER-RETURN',json.dumps(view))
    self.assertNotIn('PRIVATE-CREDENTIAL',(root/'native-integration-flows.json').read_text())
 def test_native_select_preserves_numeric_device_ids_and_validates_choices(self):
  flow={'type':'form','data_schema':[{'name':'device','required':True,'options':[[123,'PAC'],[456,'Thermostat']]}]}
  self.assertEqual(validate_values(flow,{'device':123}),{'device':123})
  for value in ('123',789):self.assertRaises(ValueError,validate_values,flow,{'device':value})
 def test_menus_booleans_numbers_and_multiselect(self):
  self.assertEqual(validate_values({'type':'menu','menu_options':['automatic','manual']},{'next_step_id':'manual'}),{'next_step_id':'manual'})
  self.assertRaises(ValueError,validate_values,{'type':'menu','menu_options':['automatic']},{'next_step_id':'foreign'})
  flow={'type':'form','data_schema':[{'name':'port','required':True,'selector':{'number':{'min':1,'max':65535}}},{'name':'verify_ssl','type':'boolean','default':True},{'name':'modes','type':'multi_select','options':{'heat':'Chauffage'}}]}
  self.assertEqual(schema_fields(flow)[1]['default'],True)
  validate_values(flow,{'port':80,'verify_ssl':True,'modes':['heat']})
  for values in ({'port':0},{'port':80,'verify_ssl':'false'},{'port':80,'modes':['foreign']}):self.assertRaises(ValueError,validate_values,flow,values)
 def test_manual_device_addresses_are_local_not_supervisor_cloud_or_metadata(self):
  flow={'type':'form','data_schema':[{'name':'host','required':True}]}
  for host in ('192.168.6.20','10.0.0.2','envoy.local'):validate_values(flow,{'host':host})
  for host in ('127.0.0.1','169.254.169.254','172.30.32.1','8.8.8.8','https://evil.invalid','supervisor','::1'):self.assertRaises(ValueError,validate_values,flow,{'host':host})
 def test_foreign_session_owner_or_handler_cannot_adopt_flow(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture();f.start(root);session=f.session
   f.session=str(uuid.uuid4());self.assertRaises(RuntimeError,f.start,root);f.session=session
   self.assertRaises(ValueError,f.run,root,'flow_resume',ownerScope='invalid')
   self.assertRaises(RuntimeError,f.run,root,'flow_resume',ownerScope='b'*64)
   f.flow['handler']='ring';self.assertRaises(RuntimeError,f.run,root,'flow_resume')
 def test_repeat_start_reuses_lease_and_unknown_submit_is_never_replayed(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture(schema=[{'name':'password','required':True}]);f.start(root);f.start(root)
   self.assertEqual(sum(p=='/config/config_entries/flow'for p,k in f.calls),1)
   f.reply=TimeoutError();self.assertRaises(RuntimeError,f.advance,root,{'password':'private'})
   self.assertRaises(RuntimeError,f.advance,root,{'password':'private'});self.assertRaises(RuntimeError,f.run,root,'flow_resume')
   self.assertEqual(sum(k.get('method')=='POST'and p.endswith('/flow_fixture')for p,k in f.calls),1)
 def test_actual_created_entry_required_before_success(self):
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture();root=Path(directory);f.start(root);f.reply={'type':'create_entry','handler':f.domain,'result':{'entry_id':'entry_fixture'}}
   self.assertRaises(RuntimeError,f.advance,root,{})
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture();root=Path(directory);f.start(root);f.native=[{'entry_id':'entry_fixture','domain':f.domain,'state':'loaded'}];f.reply={'type':'create_entry','handler':f.domain,'result':{'entry_id':'entry_fixture'}}
   self.assertEqual(f.advance(root,{})['flow']['kind'],'create_entry');self.assertEqual(json.loads((root/'native-integration-flows.json').read_text()),{})
 def test_cloud_consent_and_exact_flow_operations_only(self):
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture('midea');root=Path(directory);self.assertRaises(ValueError,f.run,root,'flow_start',cloudConsent=False)
   self.assertRaises(ValueError,f.run,root,'flow_start',cloudConsent=True,service='climate.set_temperature')
   self.assertRaises(ValueError,f.run,root,'flow_start',cloudConsent=True,host='https://evil.invalid')
 def test_public_forms_discard_credentials_defaults_errors_and_unknown_properties(self):
  result=public_flow({'type':'form','handler':'ring','flow_id':'fixture','step_id':'user','data_schema':[{'name':'password','default':'SECRET'}],'errors':{'base':'SECRET'},'password':'SECRET'},'ring')
  self.assertNotIn('SECRET',json.dumps(result));self.assertTrue(result['retry'])
 def test_external_authorization_is_bound_to_the_exact_native_state_and_current_owner(self):
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture('netatmo');root=Path(directory);f.flow.update(type='external',url='https://auth.vendor.example/authorize?state=signed-native-state',step_id='auth');f.start(root)
   for changes in ({'state':'other'},{'flowId':'other'},{'ownerScope':'b'*64}):
    self.assertRaises((ValueError,RuntimeError),f.run,root,'flow_authorize',**({'flowId':'flow_fixture','state':'signed-native-state','code':'PRIVATE-CODE'}|changes))
   original=f.call
   def callback(path,**kwargs):
    if path.startswith('/auth/external/callback?'):
     self.assertEqual(kwargs,{'_configuration_callback':True});self.assertIn('state=signed-native-state',path);f.flow.update(type='external_done',step_id='creation');return {'callbackAccepted':True}
    return original(path,**kwargs)
   f.call=callback
   result=f.run(root,'flow_authorize',flowId='flow_fixture',state='signed-native-state',code='PRIVATE-CODE')
   self.assertEqual(result['flow']['kind'],'external_done');self.assertNotIn('PRIVATE-CODE',(root/'native-integration-flows.json').read_text())
 def test_native_french_instructions_are_returned_without_provider_error_bodies(self):
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture('hue');f.registry=lambda msg:{'resources':{'component.hue.config.step.user.description':'Appuyez sur le bouton de {name}.'}}if msg['type']=='frontend/get_translations'else[]
   self.assertEqual(f.start(Path(directory))['flow']['description'],'Appuyez sur le bouton de votre appareil.')
 def test_only_external_https_authorization_urls_are_exposed(self):
  for url in ('http://vendor.example','javascript:alert(1)','https://127.0.0.1','https://user:password@vendor.example','https://supervisor.local'):self.assertIsNone(authorization_url(url))
  self.assertEqual(authorization_url('https://auth.vendor.example/authorize?state=opaque'),'https://auth.vendor.example/authorize?state=opaque')

if __name__=='__main__':unittest.main()
