import importlib.util
import sys
import types
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
if 'websocket' not in sys.modules: sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('local_config_agent',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)

class LocalConfiguration(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'config.json'
        self.patch=patch.object(agent,'LOCAL_CONFIGURATION_PATH',self.path);self.patch.start()
        self.value={'version':1,'agentId':'box-a','installationId':'site-a','revision':'a'*64,
                    'configuration':{'electricalSupply':'three','equipmentRoles':[{'id':'ce','name':'Chauffe-eau'}],'devices':{},'automations':{}}}
    def tearDown(self):
        self.patch.stop();self.directory.cleanup()
    def test_persist_restart_and_no_write_when_unchanged(self):
        self.assertTrue(agent.store_local_configuration(self.value,'box-a'))
        modified=self.path.stat().st_mtime_ns
        self.assertFalse(agent.store_local_configuration(self.value,'box-a'))
        self.assertEqual(self.path.stat().st_mtime_ns,modified)
        self.assertEqual(json.loads(self.path.read_text()),self.value)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        with patch.object(agent,'request_json') as request:
            agent.publish_local_configuration('local-secret','box-a',force=True)
            payload=request.call_args.kwargs['payload']
            self.assertEqual(payload['attributes']['configuration'],self.value['configuration'])
            self.assertNotIn('local-secret',json.dumps(payload))
    def test_other_enrollment_and_invalid_response_preserve_copy(self):
        agent.store_local_configuration(self.value,'box-a')
        original=self.path.read_bytes()
        for value in ({**self.value,'agentId':'box-b'},{**self.value,'version':2},{**self.value,'configuration':{'token':'secret'}}):
            with self.assertRaises(ValueError):agent.store_local_configuration(value,'box-a')
            self.assertEqual(self.path.read_bytes(),original)
        with patch.object(agent,'request_json') as request:
            agent.publish_local_configuration('token','box-b',force=True)
            request.assert_not_called()
    def test_failed_replace_keeps_previous_copy(self):
        agent.store_local_configuration(self.value,'box-a')
        original=self.path.read_bytes()
        with patch.object(agent.os,'replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): agent.store_local_configuration({**self.value,'revision':'b'*64},'box-a')
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(len(list(self.path.parent.iterdir())),1)
    def test_portal_is_not_needed_for_republication(self):
        agent.store_local_configuration(self.value,'box-a')
        with patch.object(agent,'request_json') as request:
            agent.publish_local_configuration('token','box-a',force=True)
            self.assertEqual(request.call_args.args[0],'http://supervisor/core/api/states/sensor.home_local_configuration')

    def test_revision_is_acknowledged_in_fast_inventory_without_private_configuration(self):
        state={'entity_id':'sensor.home_local_configuration','state':'a'*64,
               'attributes':{'configuration':self.value['configuration']}}
        with patch.object(agent,'request_json',side_effect=[{'version':'test'},[state]]), patch.object(agent,'maintain_daily_pv_peak'):
            summary=agent.home_assistant_summary('token',full_inventory=False)
        self.assertEqual(summary['inventory'][0]['state'],'a'*64)
        self.assertNotIn('configuration',summary['inventory'][0]['attributes'])

if __name__=='__main__':unittest.main()
