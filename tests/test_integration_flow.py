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
 def test_missing_application_credentials_open_the_native_credential_journey(self):
  with tempfile.TemporaryDirectory()as directory:
   f=Fixture('netatmo');root=Path(directory);f.flow={'type':'abort','handler':'netatmo','reason':'missing_credentials'}
   calls=[]
   def registry(message):
    calls.append(message)
    if message['type']=='application_credentials/config':return {'domains':['netatmo']}
    if message['type']=='application_credentials/create':
     f.flow={'type':'form','handler':'netatmo','flow_id':'flow_fixture','step_id':'pick_implementation','data_schema':[]};return {'client_secret':'PRIVATE-SECRET'}
    return []
   f.registry=registry;view=f.start(root);self.assertEqual(view['flow']['step'],'application_credentials');self.assertEqual(view['flow']['fields'][1]['kind'],'secret')
   self.assertEqual(f.run(root,'flow_resume')['flow']['step'],'application_credentials')
   self.assertRaises(ValueError,f.run,root,'flow_advance',flowId='application_credentials',step='application_credentials',cloudConsent=True,values={'client_id':'id','client_secret':'PRIVATE-SECRET','domain':'other'})
   result=f.run(root,'flow_advance',flowId='application_credentials',step='application_credentials',cloudConsent=True,values={'client_id':'id','client_secret':'PRIVATE-SECRET'})
   self.assertEqual(result['flow']['step'],'pick_implementation');self.assertEqual(sum(x['type']=='application_credentials/create'for x in calls),1)
   self.assertNotIn('PRIVATE-SECRET',json.dumps(result));self.assertNotIn('PRIVATE-SECRET',(root/'native-integration-flows.json').read_text())
 def test_explicit_same_owner_reclaim_reads_form_without_replaying_a_submission(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea',[{'name':'password','required':True}]);f.start(root);old=f.session;f.session=str(uuid.uuid4());before=len(f.calls)
   self.assertRaises(RuntimeError,f.start,root)
   self.assertRaises(RuntimeError,f.run,root,'flow_reclaim',cloudConsent=True,confirmed=False)
   self.assertRaises(RuntimeError,f.run,root,'flow_reclaim',cloudConsent=True,confirmed=True,ownerScope='b'*64)
   view=f.run(root,'flow_reclaim',cloudConsent=True,confirmed=True)
   self.assertEqual(view['flow']['step'],'user');self.assertFalse(any(k.get('method')in('POST','DELETE')for p,k in f.calls[before:]))
   f.session=old;self.assertRaises(RuntimeError,f.run,root,'flow_resume')
 def test_reclaim_never_replays_uncertain_credentials_or_missing_native_flow(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea',[{'name':'password','required':True}]);f.start(root);f.reply=TimeoutError();self.assertRaises(RuntimeError,f.advance,root,{'password':'PRIVATE'});f.session=str(uuid.uuid4());before=len(f.calls)
   self.assertRaises(RuntimeError,f.run,root,'flow_reclaim',cloudConsent=True,confirmed=True);self.assertFalse(any(k.get('method')in('POST','DELETE')for p,k in f.calls[before:]))
  with tempfile.TemporaryDirectory()as directory:
   import urllib.error
   root=Path(directory);f=Fixture('midea');f.start(root);f.session=str(uuid.uuid4());original=f.call
   def missing(path,**kw):
    if path.endswith('/flow_fixture'):raise urllib.error.HTTPError(path,404,'Not Found',{},None)
    return original(path,**kw)
   f.call=missing;view=f.run(root,'flow_reclaim',cloudConsent=True,confirmed=True);self.assertEqual(view['flow']['kind'],'cancelled');self.assertEqual(json.loads((root/'native-integration-flows.json').read_text()),{})
 def test_expired_ready_lease_can_be_reclaimed_only_with_cloud_consent(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea');f.start(root);path=root/'native-integration-flows.json';journal=json.loads(path.read_text());journal['midea']['expiresAt']=0;path.write_text(json.dumps(journal));f.session=str(uuid.uuid4())
   self.assertRaises(ValueError,f.run,root,'flow_reclaim',cloudConsent=False,confirmed=True)
   self.assertEqual(f.run(root,'flow_reclaim',cloudConsent=True,confirmed=True)['flow']['kind'],'form')
 def test_completed_flow_missing_from_native_api_returns_actual_connected_devices_without_replaying_login(self):
  import urllib.error
  for operation in ('flow_start','flow_resume','flow_reclaim','flow_cancel'):
   with self.subTest(operation=operation),tempfile.TemporaryDirectory()as directory:
    root=Path(directory);f=Fixture('midea');f.start(root);original=f.call
    f.native=[{'entry_id':'entry_pac','domain':'midea','state':'loaded'}]
    def missing(path,**kw):
     if path.endswith('/flow_fixture'):raise urllib.error.HTTPError(path,404,'Not Found',{},None)
     return original(path,**kw)
    f.call=missing;before=len(f.calls);extra={'cloudConsent':True}if operation=='flow_start'else{'cloudConsent':True,'confirmed':True}if operation=='flow_reclaim'else{}
    result=f.run(root,operation,**extra);self.assertEqual(result['entries'][0]['entryId'],'entry_pac');self.assertTrue(result['pairingReady']);self.assertEqual(result['flow']['reason'],'flow_finished');self.assertEqual(json.loads((root/'native-integration-flows.json').read_text()),{})
    self.assertFalse(any(k.get('method')in('POST','DELETE')for p,k in f.calls[before:]))
 def test_missing_flow_after_unknown_login_releases_lease_only_after_reading_actual_entries(self):
  import urllib.error
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea',[{'name':'password','required':True}]);f.start(root);f.reply=TimeoutError();self.assertRaises(RuntimeError,f.advance,root,{'password':'PRIVATE'});original=f.call;f.session=str(uuid.uuid4())
   def missing(path,**kw):
    if path.endswith('/flow_fixture'):raise urllib.error.HTTPError(path,404,'Not Found',{},None)
    return original(path,**kw)
   f.call=missing;result=f.run(root,'flow_reclaim',cloudConsent=True,confirmed=True);self.assertEqual(result['devices'],[]);self.assertFalse(result['pairingReady']);self.assertEqual(result['flow']['kind'],'cancelled');self.assertNotIn('PRIVATE',json.dumps(result))
 def test_missing_flow_does_not_clear_lease_if_actual_entries_are_unavailable(self):
  import urllib.error
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea');f.start(root);original=f.call
   def unavailable(path,**kw):
    if path.endswith('/flow_fixture'):raise urllib.error.HTTPError(path,404,'Not Found',{},None)
    if path=='/config/config_entries/entry':raise ConnectionError()
    return original(path,**kw)
   f.call=unavailable;self.assertRaises(ConnectionError,f.run,root,'flow_resume');self.assertIn('midea',json.loads((root/'native-integration-flows.json').read_text()))
 def test_cloud_submission_has_time_to_finish_but_is_never_replayed(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);f=Fixture('midea',[{'name':'password','required':True}]);f.start(root);f.reply=TimeoutError();self.assertRaises(RuntimeError,f.advance,root,{'password':'PRIVATE'});posts=[k for p,k in f.calls if p.endswith('/flow_fixture')and k.get('method')=='POST'];self.assertEqual(len(posts),1);self.assertEqual(posts[0]['timeout'],45)
 def test_public_failures_are_fixed_codes_never_vendor_text_or_credentials(self):
  from integration_flow import public_failure
  self.assertEqual(public_failure(RuntimeError('Reprenez la connexion dans la session qui l’a ouverte.')),'native_connection_resume_required')
  self.assertNotIn('PRIVATE',public_failure(RuntimeError('PRIVATE vendor password rejected')))
 def test_only_external_https_authorization_urls_are_exposed(self):
  for url in ('http://vendor.example','javascript:alert(1)','https://127.0.0.1','https://user:password@vendor.example','https://supervisor.local'):self.assertIsNone(authorization_url(url))
  self.assertEqual(authorization_url('https://auth.vendor.example/authorize?state=opaque'),'https://auth.vendor.example/authorize?state=opaque')

if __name__=='__main__':unittest.main()
