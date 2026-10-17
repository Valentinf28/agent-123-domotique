import sys, tempfile, unittest, json, copy, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from local_mobile import LocalMobile, store_grants
from nacl.secret import SecretBox

class LocalMobileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  self.key=bytes(range(32));self.box=SecretBox(self.key);self.sequence=0;self.calls=[]
  self.grant={'version':1,'boxId':'box-a','installationId':'house-a','scope':'a'*64,'phones':[{'id':'phone-a','key':self.key.hex()}],'controls':['switch.selected'],'catalogs':[]}
  self.path=root/'grant';store_grants(self.grant,'box-a',self.path)
  self.current='box-a'
  self.service=LocalMobile(self.call,lambda c:[{'entity_id':'switch.other_home','platform':'tuya','device_id':'unimported'}] if c['type']=='config/entity_registry/list' else {},lambda:self.current,path=self.path,ledger=root/'replay',clock=lambda:1000)
 def call(self,path,**kw):
  self.calls.append((path,kw))
  return [{'entity_id':'sensor.pv','state':'123'},{'entity_id':'switch.other_home','state':'on'}] if path=='/states' else []
 def envelope(self,**kw):
  self.sequence+=1;nonce=self.sequence.to_bytes(24,'big')
  request={'operation':'http','method':'GET','path':'/states','scope':'a'*64,'installationId':'house-a','timestamp':1000,'requestId':nonce.hex(),**kw}
  return {'version':1,'phoneId':'phone-a','nonce':nonce.hex(),'ciphertext':self.box.encrypt(json.dumps(request).encode(),nonce).ciphertext.hex()}
 def response(self,envelope):
  p=self.service.handle(envelope);self.assertTrue(bytes.fromhex(p['nonce'])[0]&128)
  return json.loads(self.box.decrypt(bytes.fromhex(p['ciphertext']),bytes.fromhex(p['nonce'])))
 def test_local_read_without_portal_or_subscription_and_private_manifest(self):
  self.assertEqual(self.response(self.envelope())['result'],[{'entity_id':'sensor.pv','state':'123'}]);self.assertEqual(self.path.stat().st_mode&0o777,0o600)
 def test_tampering_wrong_phone_scope_house_clock_and_nonce_rejected(self):
  for changes in [{'scope':'b'*64},{'installationId':'house-b'},{'timestamp':800},{'requestId':'1'*48}]:
   with self.assertRaises(ValueError):self.service.handle(self.envelope(**changes))
  for field,value in [('phoneId','phone-b'),('ciphertext','00'*32),('nonce','ff'*24)]:
   env=self.envelope();env[field]=value
   with self.assertRaises(Exception):self.service.handle(env)
  self.assertEqual(self.calls,[])
 def test_commands_scoped_to_selected_device_and_replay_durable(self):
  env=self.envelope(method='POST',path='/services/switch/turn_on',body={'entity_id':'switch.selected'})
  first=self.service.handle(env);self.assertEqual(first,self.service.handle(env));self.assertEqual(len(self.calls),1)
  self.service.cache=None;self.assertEqual(first,self.service.handle(env));self.assertEqual(len(self.calls),1)
  for path,body in [('/services/switch/turn_on',{'entity_id':'switch.other_home'}),('/services/homeassistant/restart',{}),('/services/switch/turn_on',{'entity_id':'switch.selected','area_id':'all'}),('/config',{})]:
   self.assertFalse(self.response(self.envelope(method='POST',path=path,body=body))['ok'])
  self.assertEqual(len(self.calls),1)
 def test_uncertain_command_is_never_executed_twice(self):
  env=self.envelope(method='POST',path='/services/switch/toggle',body={'entity_id':'switch.selected'})
  digest=hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest();self.service.reserve('phone-a',env['nonce'],digest)
  with self.assertRaisesRegex(ValueError,'result must be checked'):self.service.handle(env)
  self.assertEqual(self.calls,[])
 def test_revoked_phone_and_changed_box_refused(self):
  self.grant['phones']=[];store_grants(self.grant,'box-a',self.path)
  with self.assertRaises(ValueError):self.service.handle(self.envelope())
  self.grant['phones']=[{'id':'phone-a','key':self.key.hex()}];store_grants(self.grant,'box-a',self.path);self.current='box-b'
  with self.assertRaises(ValueError):self.service.handle(self.envelope())
 def test_history_cannot_escape_to_administration(self):
  for path in ['/history/period/%2e%2e%2fconfig?filter_entity_id=sensor.pv','//evil/states','/history/period/2026-10-16T00%3A00%3A00Z?filter_entity_id=switch.other_home','/history/period/2026-10-16T00%3A00%3A00Z?filter_entity_id=sensor.pv&other=1']:
   self.assertFalse(self.response(self.envelope(path=path))['ok'])
  self.assertEqual(self.calls,[])
  self.assertTrue(self.response(self.envelope(path='/history/period/2026-10-16T00%3A00%3A00.000Z?filter_entity_id=sensor.pv&minimal_response='))['ok'])
 def test_readonly_statistics_reject_unselected_and_admin_commands(self):
  for command in [{'type':'config/entity_registry/list'},{'type':'recorder/statistics_during_period','statistic_ids':['switch.other_home']},{'type':'recorder/statistics_during_period','statistic_ids':['sensor.pv'],'device_id':'anything'}]:
   self.assertFalse(self.response(self.envelope(operation='websocket',command=command))['ok'])
 def test_invalid_manifest_never_replaces_existing_authority(self):
  old=self.path.read_bytes()
  for mutate in [lambda g:g.update(boxId='foreign'),lambda g:g.update(scope='bad'),lambda g:g.update(phones=g['phones']*2)]:
   value=copy.deepcopy(self.grant);mutate(value)
   with self.assertRaises(ValueError):store_grants(value,'box-a',self.path)
   self.assertEqual(self.path.read_bytes(),old)

 def test_revocation_during_registry_read_blocks_command_delivery(self):
  def registry(command):
   self.grant['phones']=[];store_grants(self.grant,'box-a',self.path);return []
  self.service.registry=registry
  result=self.response(self.envelope(method='POST',path='/services/switch/turn_on',body={'entity_id':'switch.selected'}))
  self.assertFalse(result['ok']);self.assertEqual(self.calls,[])
