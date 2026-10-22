from pathlib import Path
import sys,tempfile,json,unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from overkiz_setup import configure,valid_local_host
OWNER='a'*64;SESSION='123e4567-e89b-42d3-a456-426614174000'
def form(step,fields):return {'type':'form','step_id':step,'handler':'overkiz','flow_id':'flow1','data_schema':[{'name':name,**extra} for name,extra in fields]}
HUB=form('user',[('hub',{'options':[['somfy_europe','Somfy Europe'],['rexel','Rexel'],['somfy_developer_mode','Somfy local']]})])
MODE=form('local_or_cloud',[('api_type',{'options':[['local','Local'],['cloud','Cloud']]})])
CLOUD=form('cloud',[('username',{}),('password',{})])
LOCAL=form('local',[('host',{}),('token',{}),('verify_ssl',{})])
ENTRY={'entry_id':'entry1','domain':'overkiz','state':'loaded'}
class OverkizTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
 def run_step(self,op,call,**payload):return configure({'operation':op,'ownerScope':OWNER,**({'session':SESSION} if op!='status' else {}),**payload},call,data=self.data,now=100)
 def start(self):
  result=self.run_step('start',Mock(side_effect=[[],HUB]));state=json.loads((self.data/'overkiz-flow.json').read_text());state['selectedHub']='somfy_europe';(self.data/'overkiz-flow.json').write_text(json.dumps(state));return result
 def test_status_is_read_only(self):
  call=Mock(return_value=[ENTRY]);result=self.run_step('status',call);self.assertEqual(result['status'],'existing');self.assertFalse(result['devicesVerified']);self.assertEqual(call.call_count,1);self.assertFalse(list(self.data.iterdir()))
 def test_start_native_somfy_choices_private_journal(self):
  call=Mock(side_effect=[[],HUB]);result=self.run_step('start',call);self.assertEqual(result['status'],'hub');self.assertEqual([c['id'] for c in result['choices']],['somfy_europe','somfy_developer_mode']);self.assertEqual(call.call_args.kwargs['payload'],{'handler':'overkiz','show_advanced_options':False});self.assertEqual((self.data/'overkiz-flow.json').stat().st_mode&0o777,0o600)
 def test_existing_connection_never_replaced(self):
  call=Mock(return_value=[ENTRY]);self.assertEqual(self.run_step('start',call)['status'],'existing');self.assertEqual(call.call_count,1)
 def test_native_hub_and_mode(self):
  self.start();call=Mock(side_effect=[[],HUB,MODE]);self.assertEqual(self.run_step('hub',call,hub='somfy_europe')['status'],'mode');self.assertEqual(call.call_args.kwargs['payload'],{'hub':'somfy_europe'})
  call=Mock(side_effect=[[],MODE,LOCAL]);self.assertEqual(self.run_step('mode',call,mode='local')['status'],'local');self.assertEqual(call.call_args.kwargs['payload'],{'api_type':'local'})
 def test_other_provider_never_submitted(self):
  self.start();call=Mock(side_effect=[[],HUB]);self.assertEqual(self.run_step('hub',call,hub='rexel')['status'],'needs_help');self.assertEqual(call.call_count,2)
 def test_unknown_native_fields_and_oauth_refused(self):
  self.start()
  for flow in [CLOUD|{'data_schema':CLOUD['data_schema']+[{'name':'url'}]},CLOUD|{'step_id':'oauth'},CLOUD|{'handler':'tuya'}]:
   call=Mock(side_effect=[[],flow]);self.assertEqual(self.run_step('credentials',call,username='u',password='p',cloudConsent=True)['status'],'needs_help');self.assertEqual(call.call_count,2)
 def test_cloud_consent_and_no_secrets(self):
  self.start();call=Mock(side_effect=[[],CLOUD]);self.assertEqual(self.run_step('credentials',call,username='user@example.test',password='secret',cloudConsent=False)['status'],'needs_help');self.assertEqual(call.call_count,2)
  call=Mock(side_effect=[[],CLOUD,CLOUD|{'errors':{'base':'invalid_auth'},'description_placeholders':{'secret':'secret'}}]);result=self.run_step('credentials',call,username='user@example.test',password='secret',cloudConsent=True);self.assertTrue(result['retry']);self.assertNotIn('secret',json.dumps(result));self.assertNotIn('user@example.test',(self.data/'overkiz-flow.json').read_text());self.assertNotIn('secret',(self.data/'overkiz-flow.json').read_text())
 def test_local_tls_mandatory_and_hostname_only(self):
  self.start()
  for host,ssl in [('http://evil.test',True),('127.0.0.1',True),('gateway-1234-1234-1234.local',False)]:
   call=Mock(side_effect=[[],LOCAL]);self.assertEqual(self.run_step('local',call,host=host,token='secret',verifySsl=ssl)['status'],'needs_help');self.assertEqual(call.call_count,2)
  call=Mock(side_effect=[[],LOCAL,LOCAL|{'errors':{'base':'certificate_verify_failed'}}]);result=self.run_step('local',call,host='gateway-1234-1234-1234.local:8443',token='secret',verifySsl=True);self.assertTrue(result['retry']);self.assertIs(call.call_args.kwargs['payload']['verify_ssl'],True);self.assertNotIn('secret',(self.data/'overkiz-flow.json').read_text())
 def test_entry_creation_requires_verification_and_duplicate_start_does_not_post(self):
  self.start();call=Mock(side_effect=[[],CLOUD,{'type':'create_entry','result':{'entry_id':'entry1','data':{'password':'secret'}}},[ENTRY]]);result=self.run_step('credentials',call,username='u',password='secret',cloudConsent=True);self.assertEqual(result['status'],'configured');self.assertNotIn('secret',json.dumps(result));call=Mock(return_value=[ENTRY]);self.assertEqual(self.run_step('start',call)['status'],'configured');self.assertEqual(call.call_count,1)
 def test_owner_session_and_cancel_isolation(self):
  self.start();call=Mock(return_value=[]);result=configure({'operation':'cancel','ownerScope':'b'*64,'session':SESSION},call,data=self.data,now=100);self.assertEqual(result['status'],'needs_help');self.assertEqual(call.call_count,1)
  call=Mock(side_effect=[[],{}]);self.assertEqual(self.run_step('cancel',call)['status'],'cancelled');self.assertEqual(call.call_args.kwargs['method'],'DELETE')
 def test_lost_start_never_recreated(self):
  call=Mock(side_effect=[[],TimeoutError('secret')]);self.assertEqual(self.run_step('start',call)['status'],'needs_help');call=Mock(return_value=[]);self.assertEqual(self.run_step('start',call)['status'],'needs_help');self.assertEqual(call.call_count,1)
 def test_lost_post_resumes_advanced_native_step_without_replay(self):
  self.start();call=Mock(side_effect=[[],HUB,TimeoutError('secret')]);self.assertEqual(self.run_step('hub',call,hub='somfy_europe')['status'],'needs_help');call=Mock(side_effect=[[],MODE]);self.assertEqual(self.run_step('hub',call,hub='somfy_europe')['status'],'mode');self.assertEqual(call.call_count,2)
  call=Mock(side_effect=[[],MODE,CLOUD]);self.assertEqual(self.run_step('mode',call,mode='cloud')['status'],'credentials');self.assertEqual(call.call_args.kwargs['payload'],{'api_type':'cloud'})
 def test_lost_creation_detects_existing_without_claiming_unverified_ownership(self):
  self.start();self.run_step('credentials',Mock(side_effect=[[],CLOUD,TimeoutError('secret')]),username='u',password='secret',cloudConsent=True);call=Mock(return_value=[ENTRY]);self.assertEqual(self.run_step('start',call)['status'],'existing');self.assertEqual(call.call_count,1)
 def test_expired_owner_flow_aborted_before_new_start(self):
  self.start();call=Mock(side_effect=[[],{},HUB]);result=configure({'operation':'start','ownerScope':OWNER,'session':SESSION},call,data=self.data,now=800);self.assertEqual(result['status'],'hub');self.assertEqual(call.call_args_list[1].kwargs['method'],'DELETE')
 def test_foreign_expired_flow_not_cancelled(self):
  self.start();call=Mock(return_value=[]);result=configure({'operation':'start','ownerScope':'b'*64,'session':SESSION},call,data=self.data,now=800);self.assertEqual(result['status'],'needs_help');self.assertEqual(call.call_count,1)
 def test_concurrent_existing_entry_blocks_any_new_mutation(self):
  self.start();call=Mock(return_value=[ENTRY]);self.assertEqual(self.run_step('credentials',call,username='u',password='secret',cloudConsent=True)['status'],'existing');self.assertEqual(call.call_count,1)
 def test_unknown_payload_rejected_before_network(self):
  call=Mock()
  with self.assertRaises(ValueError):self.run_step('status',call,url='https://evil.test')
  call.assert_not_called()
if __name__=='__main__':unittest.main()
