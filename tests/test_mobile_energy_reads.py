import copy, importlib.util, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent_123_domotique'))
spec=importlib.util.spec_from_file_location('energy_read_agent',ROOT/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
from local_mobile import LocalMobile,store_grants
from nacl.secret import SecretBox

class MobileEnergyReadTests(unittest.TestCase):
 def setUp(self):
  self.old={'entity_id':'sensor.hybrid_pv_power','state':'0','attributes':{'device_class':'power','unit_of_measurement':'W'},'last_reported':'2026-10-23T00:00:00+00:00','last_updated':'2026-10-23T00:00:00+00:00'}
  self.fresh={**self.old,'last_reported':'2026-10-24T12:00:00+00:00'}
  self.other={'entity_id':'switch.other_home','state':'on','attributes':{}}
  self.meta={'sensor.hybrid_pv_power':{'platform':'solarman','original_name':'PV Power','model':'SG01HP3','serial_number':'fixture','area_name':'Private room','device_name':'Private device'}}
  self.calls=[]
 def request(self,url,**kwargs):
  self.calls.append((url,kwargs))
  if url.endswith('/states'):return copy.deepcopy([self.old,self.other])
  if url.endswith('/template'):return json.dumps([self.fresh])
  return {'forwarded':True}
 def context(self):
  stack=ExitStack();stack.enter_context(patch.object(agent,'request_json',side_effect=self.request));stack.enter_context(patch.object(agent,'home_assistant_registry_metadata',return_value=self.meta));return stack
 def assert_energy(self,row):
  self.assertEqual(row['state'],'0');self.assertEqual(row['last_reported'],self.fresh['last_reported']);self.assertEqual(row['last_updated'],self.old['last_updated'])
  self.assertEqual(row['attributes']['serial_number'],'fixture');self.assertNotIn('area_name',row['attributes']);self.assertNotIn('device_name',row['attributes'])
 def test_relay_dispatch_uses_real_report_and_registry_without_added_rows(self):
  with self.context(),patch('installation_reset.blocks_mutations',return_value=False):
   response=agent.relay_command('fixture',{'id':'fixture-read','action':'ha.states'})
  self.assertTrue(response['ok']);self.assertEqual(len(response['result']),2);self.assert_energy(response['result'][0]);self.assertEqual(response['result'][1],self.other)
  self.assertEqual([kw.get('method','GET') for _,kw in self.calls],['GET','POST'])
  self.assertEqual(set(self.calls[1][1]['payload']),{'template'})
 def test_encrypted_local_reads_share_normalizer_and_keep_foreign_home_hidden(self):
  with tempfile.TemporaryDirectory() as tmp,self.context():
   root=Path(tmp);key=bytes(range(32));box=SecretBox(key)
   store_grants({'version':1,'boxId':'box-a','installationId':'home-a','scope':'a'*64,'phones':[{'id':'phone-a','key':key.hex()}],'controls':[],'catalogs':[]},'box-a',root/'grants')
   service=LocalMobile(lambda path,**kw:agent.mobile_home_assistant_call('fixture',path,**kw),lambda c:[{'entity_id':'switch.other_home','platform':'tuya','device_id':'foreign'}] if c['type']=='config/entity_registry/list' else {},lambda:'box-a',path=root/'grants',ledger=root/'ledger',clock=lambda:1000)
   nonce=(1).to_bytes(24,'big');request={'operation':'http','method':'GET','path':'/states','scope':'a'*64,'installationId':'home-a','timestamp':1000,'requestId':nonce.hex()}
   envelope={'version':1,'phoneId':'phone-a','nonce':nonce.hex(),'ciphertext':box.encrypt(json.dumps(request).encode(),nonce).ciphertext.hex()}
   encoded=service.handle(envelope);response=json.loads(box.decrypt(bytes.fromhex(encoded['ciphertext']),bytes.fromhex(encoded['nonce'])))
   self.assertTrue(response['ok']);self.assertEqual(len(response['result']),1);self.assert_energy(response['result'][0])
 def test_template_unavailable_keeps_old_timestamp_and_registry_failure_no_fake_identity(self):
  def request(url,**kw):
   if url.endswith('/template'):raise RuntimeError('offline')
   return [copy.deepcopy(self.old)]
  with patch.object(agent,'request_json',side_effect=request),patch.object(agent,'home_assistant_registry_metadata',return_value={}):
   self.assertEqual(agent.mobile_home_assistant_states('fixture'),[self.old])
 def test_registry_failure_preserves_all_readable_rows_without_inventing_identity(self):
  for value in (RuntimeError('offline'),None):
   with patch.object(agent,'request_json',side_effect=self.request),patch.object(agent,'home_assistant_registry_metadata',side_effect=value if isinstance(value,Exception) else None,return_value=value):
    rows=agent.mobile_home_assistant_states('fixture')
   self.assertEqual(len(rows),2);self.assertEqual(rows[0],self.fresh);self.assertEqual(rows[1],self.other)
   self.assertNotIn('platform',rows[0]['attributes'])
 def test_non_read_paths_unchanged_and_bad_states_rejected(self):
  with self.context():
   self.assertEqual(agent.mobile_home_assistant_call('fixture','/services/light/turn_on',method='POST',payload={'entity_id':'light.test'}),{'forwarded':True})
  self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][1]['payload'],{'entity_id':'light.test'})
  with patch.object(agent,'request_json',return_value={}):
   with self.assertRaises(RuntimeError):agent.mobile_home_assistant_states('fixture')
if __name__=='__main__':unittest.main()
