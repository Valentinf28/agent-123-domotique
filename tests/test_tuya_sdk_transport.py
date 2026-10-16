"""Exercise the real pinned SDK request path without network or real tokens."""
import importlib.util
import time
import unittest
from unittest.mock import patch, Mock
from tuya_homes import _api

@unittest.skipUnless(importlib.util.find_spec('tuya_sharing'), 'Pinned SDK required')
class TransportTests(unittest.TestCase):
 def data(self):
  return {'endpoint':'https://apigw.tuyaeu.com','user_code':'synthetic','token_info':{'access_token':'synthetic-access','refresh_token':'synthetic-refresh','t':int(time.time()*1000),'expire_time':3600}}
 def test_real_sdk_timeout_is_overridden_without_duplicate_keyword(self):
  response=Mock(ok=True);response.json.return_value={'success':True,'result':[]}
  with patch('requests.sessions.Session.request',return_value=response) as request:
   api=_api(self.data())
   self.assertEqual(api.get('/v1.0/m/life/users/homes')['result'],[])
   self.assertEqual(api.get('/v1.0/m/life/ha/home/devices',{'homeId':'1'})['result'],[])
   self.assertEqual(request.call_count,2)
   for call in request.call_args_list:
    self.assertEqual(call.kwargs['timeout'],4)
    self.assertFalse(call.kwargs['allow_redirects'])
   api.session.close()
 def test_other_paths_and_mutations_never_reach_transport(self):
  with patch('requests.sessions.Session.request') as request:
   api=_api(self.data())
   with self.assertRaises(ValueError):api.get('/forbidden')
   with self.assertRaises(ValueError):api.post('/v1.0/m/life/users/homes',{})
   request.assert_not_called();api.session.close()
 def test_expired_credentials_are_not_refreshed(self):
  data=self.data();data['token_info']['t']=0
  with patch('requests.sessions.Session.request') as request:
   api=_api(data)
   with self.assertRaises(ValueError):api.get('/v1.0/m/life/users/homes')
   request.assert_not_called();api.session.close()
if __name__=='__main__':unittest.main()
