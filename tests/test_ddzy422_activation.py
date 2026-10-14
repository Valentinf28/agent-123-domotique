import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock
from ddzy422_setup import install, DOMAIN
from ddzy422_activation import activate

OWNER='1'*64
READY={'domain':DOMAIN,'version':'0.1.0','is_built_in':False}
class ActivationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name);self.config=root/'config';self.config.mkdir();self.data=root/'data';install(self.config)
 def run_activation(self,call,operation='activate',manifest=None,**kwargs):
  return activate({'operation':operation,'ownerScope':OWNER,**({'confirmed':True} if operation=='activate' else {})},call,loaded_manifest=manifest,authorize=kwargs.pop('authorize',lambda:{'is_admin':True}),config=self.config,data=self.data,now=kwargs.pop('now',1000),**kwargs)
 def test_status_readiness_never_writes_or_restarts(self):
  call=Mock(return_value=[]);self.assertEqual(self.run_activation(call,'status')['status'],'restart_required');self.assertFalse(self.data.exists());self.assertEqual(call.call_count,1)
 def test_ready_no_restart_or_journal(self):
  call=Mock(return_value=[DOMAIN]);self.assertEqual(self.run_activation(call,manifest=READY)['status'],'ready');self.assertFalse((self.data/'ddzy422-activation.json').exists());self.assertEqual(call.call_count,1)
 def test_confirmation_required_before_any_request(self):
  call=Mock()
  with self.assertRaises(ValueError):activate({'operation':'activate','ownerScope':OWNER},call,loaded_manifest=None,authorize=lambda:{'is_admin':True},config=self.config,data=self.data)
  call.assert_not_called();self.assertFalse(self.data.exists())
 def test_foreign_or_symlink_component_never_restarts(self):
  target=self.config/'custom_components'/DOMAIN/'sensor.py';target.write_text('foreign');call=Mock()
  with self.assertRaises(RuntimeError):self.run_activation(call)
  call.assert_not_called();self.assertFalse(self.data.exists())
 def test_no_admin_no_restart(self):
  call=Mock(return_value=[])
  with self.assertRaises(RuntimeError):self.run_activation(call,authorize=lambda:{'is_admin':False})
  self.assertEqual(call.call_count,1);self.assertFalse((self.data/'ddzy422-activation.json').exists())
 def test_lost_restart_response_not_repeated_across_process(self):
  call=Mock(side_effect=[[],TimeoutError()]);result=self.run_activation(call)
  self.assertEqual(result['status'],'activation_pending');self.assertEqual(json.loads((self.data/'ddzy422-activation.json').read_text())['ownerScope'],OWNER)
  retry=Mock(return_value=[]);self.assertEqual(self.run_activation(retry,now=1010)['status'],'activation_pending');self.assertEqual(retry.call_count,1)
  status=Mock(side_effect=TimeoutError());self.assertEqual(self.run_activation(status,'status',now=1010)['status'],'activation_pending')
 def test_cooldown_requires_new_explicit_confirmation(self):
  self.run_activation(Mock(side_effect=[[],[]]));status=Mock(return_value=[])
  self.assertEqual(self.run_activation(status,'status',now=1400)['status'],'restart_required');self.assertEqual(status.call_count,1)
  retry=Mock(side_effect=[[],[]]);self.assertEqual(self.run_activation(retry,now=1400)['status'],'activation_pending');self.assertEqual(retry.call_count,2)
 def test_explicit_refusal_is_not_reported_as_restart(self):
  error=urllib.error.HTTPError('url',403,'denied',{},None);call=Mock(side_effect=[[],error])
  with self.assertRaises(RuntimeError):self.run_activation(call)
  self.assertFalse((self.data/'ddzy422-activation.json').exists())

if __name__=='__main__':unittest.main()
