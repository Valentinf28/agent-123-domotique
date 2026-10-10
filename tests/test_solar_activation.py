from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock
sys.path.append(str(Path(__file__).parents[1]/'agent_123_domotique'))
from solar_activation import activate

class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.config=Path(self.folder.name)/'config'; self.data=Path(self.folder.name)/'data'
        marker=self.config/'custom_components/solarman/123home-bundle.json';marker.parent.mkdir(parents=True);marker.write_text('{}')
    def run_activation(self,call,now=1000,manifest=None):
        return activate(call,loaded_manifest=manifest if manifest is not None else {'domain':'solarman','version':'25.08.16','is_built_in':False},config=self.config,data=self.data,now=now)
    def test_available_connector_does_not_restart(self):
        call=Mock(return_value=['solarman'])
        self.assertEqual(self.run_activation(call)['status'],'ready');self.assertEqual(call.call_count,1)
    def test_restart_once_then_verify_after_service_return(self):
        call=Mock(side_effect=[[],[]])
        self.assertEqual(self.run_activation(call)['status'],'activation_pending')
        self.assertEqual(call.call_args.args[0],'/services/homeassistant/restart')
        waiting=Mock(return_value=[])
        self.assertEqual(self.run_activation(waiting,1001)['status'],'activation_pending');self.assertEqual(waiting.call_count,1)
        ready=Mock(return_value=['solarman'])
        self.assertEqual(self.run_activation(ready,1100)['status'],'ready');self.assertEqual(ready.call_count,1)
    def test_lost_response_still_prevents_restart_loop(self):
        with self.subTest('timeout'):
            call=Mock(side_effect=[[],TimeoutError()])
            self.assertEqual(self.run_activation(call)['status'],'activation_pending')
            retry=Mock(return_value=[]); self.run_activation(retry,1100);self.assertEqual(retry.call_count,1)
    def test_rejected_restart_is_explicit_failure(self):
        call=Mock(side_effect=[[],urllib.error.HTTPError('local',403,'forbidden',{},None)])
        with self.assertRaisesRegex(RuntimeError,'refusé'):self.run_activation(call)
        self.assertFalse((self.data/'solar-activation.json').exists())
    def test_connector_must_be_ours_before_any_restart(self):
        (self.config/'custom_components/solarman/123home-bundle.json').unlink()
        call=Mock()
        with self.assertRaises(RuntimeError):self.run_activation(call)
        call.assert_not_called()

    def test_builtin_or_wrong_version_never_declared_ready(self):
        for manifest in ({'domain':'solarman','is_built_in':True}, {'domain':'solarman','is_built_in':False,'version':'old'}, {}):
            with self.subTest(manifest=manifest):
                call=Mock(side_effect=[['solarman'], []])
                result=self.run_activation(call,manifest=manifest)
                self.assertEqual(result['status'],'activation_pending')
        self.assertTrue((self.data/'solar-activation.json').exists())
