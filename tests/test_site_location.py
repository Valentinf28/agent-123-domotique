from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.append(str(Path(__file__).parents[1]/'agent_123_domotique'))
from site_location import configure

class SiteLocationTests(unittest.TestCase):
    def setUp(self):
        self.position={'latitude':48.844724,'longitude':2.428639,'timeZone':'Europe/Paris'}
        self.config={'latitude':48.844724,'longitude':2.428639,'time_zone':'Europe/Paris'}
    def test_update_has_only_geography_and_reads_back(self):
        call=Mock(side_effect=[{'latitude':1,'longitude':1,'time_zone':'UTC'},None,self.config])
        result=configure({**self.position,'external_url':'https://unexpected.example','unit_system':'imperial'},call)
        self.assertEqual(call.call_args_list[1].args[0],{'type':'config/core/update',**self.config})
        self.assertEqual(call.call_args_list[2].args[0],{'type':'get_config'})
        self.assertTrue(result['changed']);self.assertFalse(result['weatherVerified'])
    def test_retry_after_lost_response_does_not_repeat_update(self):
        call=Mock(return_value=self.config)
        self.assertFalse(configure(self.position,call)['changed'])
        self.assertEqual([item.args[0]['type'] for item in call.call_args_list],['get_config','get_config'])
    def test_mismatch_and_read_failure_never_claim_success(self):
        for after in [{}, {'latitude':False,'longitude':2.428639,'time_zone':'Europe/Paris'},TimeoutError()]:
            with self.subTest(after=after):
                call=Mock(side_effect=[{},None,after])
                with self.assertRaises((RuntimeError,TimeoutError)):configure(self.position,call)
    def test_invalid_positions_do_not_contact_box(self):
        for value in [None,'48',False,float('nan'),float('inf'),91]:
            call=Mock()
            with self.assertRaises(ValueError):configure({**self.position,'latitude':value},call)
            call.assert_not_called()
        call=Mock()
        with self.assertRaises(ValueError):configure({**self.position,'timeZone':'unknown/invalid'},call)
        call.assert_not_called()
    def test_zero_coordinates_are_valid(self):
        config={'latitude':0,'longitude':0,'time_zone':'UTC'}
        self.assertFalse(configure({'latitude':0,'longitude':0,'timeZone':'UTC'},Mock(return_value=config))['changed'])
