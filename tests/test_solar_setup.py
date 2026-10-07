from pathlib import Path
import sys
import tempfile
import json
import unittest
from unittest.mock import Mock
sys.path.append(str(Path(__file__).parents[1]/'agent_123_domotique'))
from solar_setup import configure, settings
from connector_install import install_solarman

ADAPTERS = [{'enabled':True,'ipv4':[{'address':'192.168.6.179','network_prefix':24}]}]
PAYLOAD = {'host':'192.168.6.178','loggerSerial':2974839220,'model':'deye_sg01hp3'}
class SolarSetupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = Path(self.folder.name)/'config'; self.config.mkdir()
        self.data = Path(self.folder.name)/'data'
        install_solarman(self.config)
        (self.config/'.storage').mkdir()
        self.storage = self.config/'.storage/core.config_entries'
        self.storage.write_text(json.dumps({'data':{'entries':[]}}))
    def run_setup(self,call,payload=PAYLOAD):
        return configure(payload,ADAPTERS,call,config=self.config,data=self.data)
    def test_valid_creation_uses_fixed_readonly_profile_and_serial(self):
        call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'flow1'},{'type':'create_entry','result':{'entry_id':'entry1'}}])
        result=self.run_setup(call)
        self.assertEqual(result['entryId'],'entry1')
        self.assertFalse(result['measurementsVerified'])
        submitted=call.call_args.kwargs['payload']
        self.assertEqual(submitted['logger_serial'],2974839220)
        self.assertEqual(submitted['lookup_file'],'custom/deye_sg01hp3_readonly.yaml')
        self.assertEqual(json.loads(self.storage.read_text()),{'data':{'entries':[]}},'Never edit HA storage')
    def test_lost_response_never_repeats_creation(self):
        call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'flow1'},TimeoutError()])
        with self.assertRaises(TimeoutError): self.run_setup(call)
        retry=Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError,'déjà été envoyée'): self.run_setup(retry)
        self.assertEqual(retry.call_count,1)
    def test_existing_matching_connection_is_reused_after_lost_response(self):
        self.storage.write_text(json.dumps({'data':{'entries':[{'domain':'solarman','entry_id':'saved','options':settings(PAYLOAD,ADAPTERS)}]}}))
        call=Mock(return_value=[{'entry_id':'saved','title':'existing'}])
        self.assertEqual(self.run_setup(call)['entryId'],'saved')
        self.assertEqual(call.call_count,1)
    def test_existing_different_connection_is_preserved(self):
        self.storage.write_text(json.dumps({'data':{'entries':[{'domain':'solarman','entry_id':'old','options':{'host':PAYLOAD['host']}}]}}))
        before=self.storage.read_bytes()
        call=Mock(return_value=[{'entry_id':'old'}])
        with self.assertRaisesRegex(RuntimeError,'conservée'):self.run_setup(call)
        self.assertEqual(self.storage.read_bytes(),before)
        self.assertEqual(call.call_count,1)
    def test_invalid_targets_and_models_never_call_ha(self):
        for patch in [{'host':'8.8.8.8'},{'host':'192.168.5.1'},{'host':'192.168.6.179'},{'host':'192.168.6.255'},{'loggerSerial':True},{'loggerSerial':0},{'model':'Auto'}]:
            call=Mock()
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.run_setup(call,PAYLOAD|patch)
            call.assert_not_called()
    def test_missing_bundle_requires_preparation(self):
        (self.config/'custom_components/solarman/123home-bundle.json').unlink()
        call=Mock()
        with self.assertRaisesRegex(RuntimeError,'préparé'):self.run_setup(call)
        call.assert_not_called()
    def test_form_error_resumes_same_flow(self):
        call=Mock(side_effect=[[],{'type':'form','step_id':'user','flow_id':'flow1'},{'type':'form','errors':{'base':'cannot_connect'}}])
        with self.assertRaisesRegex(RuntimeError,'refusée'):self.run_setup(call)
        retry=Mock(side_effect=[[],{'type':'create_entry','result':{'entry_id':'created'}}])
        self.assertEqual(self.run_setup(retry)['entryId'],'created')
        self.assertEqual(retry.call_count,2)
