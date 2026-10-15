import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from factory_activation import configured,poll,PORTAL
class Tests(unittest.TestCase):
 def setUp(self):self.options={'portal_url':PORTAL,'factory_id':'factory_'+'a'*32,'factory_token':'b'*64};self.state={};self.calls=[]
 def read(self):return copy.deepcopy(self.state)
 def save(self,value):self.state=copy.deepcopy(value)
 def request(self,url,**kwargs):self.calls.append((url,kwargs));return {'status':'awaiting_activation'}
 def test_wait_no_identity_no_hardware_write(self):
  result=poll(self.options,self.read,self.save,self.request);self.assertNotIn('token',result);self.assertTrue(self.state['pending_factory_activation']['token']);self.assertEqual(self.calls[0][0],PORTAL+'/agent/factory')
 def test_lost_response_reuses_secret_on_restart(self):
  def lost(url,**kwargs):self.calls.append((url,kwargs));raise TimeoutError()
  with self.assertRaises(TimeoutError):poll(self.options,self.read,self.save,lost)
  before=self.state['pending_factory_activation']['token'];poll(self.options,self.read,self.save,self.request);self.assertEqual(before,self.calls[-1][1]['payload']['enrollmentToken'])
 def test_association_then_existing_identity_never_contacts_factory(self):
  def associated(url,**kwargs):return {'status':'associated','agentId':'box_'+'c'*32}
  result=poll(self.options,self.read,self.save,associated);self.assertEqual(result['token'],self.state['token']);self.assertNotIn('pending_factory_activation',result)
  self.options['factory_id']='invalid';self.assertEqual(poll(self.options,self.read,self.save,self.request),result);self.assertEqual(self.calls,[])
 def test_invalid_response_or_context_does_not_enroll(self):
  for result in [{},{'status':'associated','agentId':'fake'}]:
   with self.assertRaises(ValueError):poll(self.options,self.read,self.save,lambda *a,**k:result)
  self.assertNotIn('token',self.state);self.options['factory_id']='factory_'+'f'*32
  with self.assertRaises(ValueError):poll(self.options,self.read,self.save,self.request)
 def test_only_vendor_tls_destination(self):
  self.assertFalse(configured({}))
  for origin in ['http://home.123panneaux-solaires.fr/api','https://evil.example/api',PORTAL+'?token=x']:
   with self.assertRaises(ValueError):configured({**self.options,'portal_url':origin})
if __name__=='__main__':unittest.main()
