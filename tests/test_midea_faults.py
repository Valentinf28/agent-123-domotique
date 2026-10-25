import json
import unittest
from unittest.mock import patch
from agent_123_domotique.midea_faults import MideaFaultMonitor, extract_fault

ENTRY = 'ENTRY123'
ENTITY = 'climate.pac_zone_1'
def diagnostic(code=1):
    return {'data': {'entry': {'entry_id': ENTRY, 'domain': 'midea', 'data': {'key': 'SECRET-NEVER-EXPORT'}}, 'device_attributes': {'error_code': code, 'zone1_power': True, 'zone_target_temp': [39, 25], 'tank_actual_temperature': 25.0}}}
def registry(_):
    return {'platform': 'midea', 'config_entry_id': ENTRY}

class MideaFaultTests(unittest.TestCase):
    def test_reads_only_confirmed_c3_basic_fault_byte(self):
        self.assertEqual(extract_fault(diagnostic()), 1)
        self.assertEqual(extract_fault(diagnostic(0)), 0)
        self.assertEqual(extract_fault(diagnostic(255)), 255)
    def test_rejects_default_zero_without_an_actual_basic_temperature_report(self):
        raw=diagnostic(0);raw['data']['device_attributes']['tank_actual_temperature']=None
        self.assertIsNone(extract_fault(raw))
    def test_invalid_or_foreign_diagnostics_never_clear_a_fault(self):
        for value in [None,True,'1',-1,256]:
            self.assertIsNone(extract_fault(diagnostic(value)))
        raw=diagnostic();raw['data']['entry']['domain']='other'
        self.assertIsNone(extract_fault(raw))
    def test_fault_snapshot_exports_no_config_secret_or_registry_identity(self):
        monitor=MideaFaultMonitor();monitor.refresh([ENTITY],registry,lambda _:diagnostic(7))
        result=monitor.snapshot(ENTITY)
        self.assertEqual(result['pac_fault_status'],'reported')
        self.assertEqual(result['pac_fault_code_raw'],7)
        self.assertEqual(set(result),{'pac_fault_status','pac_fault_code_raw','pac_fault_observed_at','pac_fault_source'})
        self.assertNotIn('SECRET',json.dumps(monitor.cache));self.assertNotIn(ENTRY,json.dumps(monitor.cache))
    def test_unavailable_diagnostics_remove_prior_live_fault_instead_of_claiming_success(self):
        monitor=MideaFaultMonitor();monitor.refresh([ENTITY],registry,lambda _:diagnostic())
        def fail(_):raise RuntimeError('provider SECRET')
        monitor.refresh([ENTITY],registry,fail)
        self.assertEqual(monitor.snapshot(ENTITY)['pac_fault_status'],'unknown')
        self.assertIsNone(monitor.snapshot(ENTITY)['pac_fault_code_raw'])
        self.assertNotIn('SECRET',json.dumps(monitor.cache))
    def test_stale_snapshot_never_claims_a_current_diagnostic(self):
        now=[0];monitor=MideaFaultMonitor(clock=lambda:now[0]);monitor.refresh([ENTITY],registry,lambda _:diagnostic())
        now[0]=91
        self.assertEqual(monitor.snapshot(ENTITY)['pac_fault_status'],'unknown')
    def test_zero_is_an_actual_raw_report_not_a_declaration_of_healthy_heating(self):
        monitor=MideaFaultMonitor();monitor.refresh([ENTITY],registry,lambda _:diagnostic(0))
        result=monitor.snapshot(ENTITY);self.assertEqual(result['pac_fault_status'],'not_reported');self.assertEqual(result['pac_fault_code_raw'],0)
    def test_foreign_platform_and_path_injection_never_read_diagnostics(self):
        for row in [{'platform':'other','config_entry_id':ENTRY},{'platform':'midea','config_entry_id':'../../secrets'}]:
            with self.subTest(row=row):
                monitor=MideaFaultMonitor();called=[];monitor.refresh([ENTITY],lambda _:row,lambda value:called.append(value))
                self.assertEqual(called,[]);self.assertEqual(monitor.snapshot(ENTITY)['pac_fault_status'],'unknown')
    def test_entry_replacement_during_read_invalidates_result(self):
        calls=[0]
        def changing(_):calls[0]+=1;return registry(_)if calls[0]==1 else {'platform':'midea','config_entry_id':'OTHER'}
        monitor=MideaFaultMonitor();monitor.refresh([ENTITY],changing,lambda _:diagnostic())
        self.assertEqual(monitor.snapshot(ENTITY)['pac_fault_status'],'unknown')
    def test_foreign_entry_in_diagnostics_is_refused(self):
        raw=diagnostic();raw['data']['entry']['entry_id']='OTHER'
        monitor=MideaFaultMonitor();monitor.refresh([ENTITY],registry,lambda _:raw)
        self.assertEqual(monitor.snapshot(ENTITY)['pac_fault_status'],'unknown')
    def test_two_zones_share_one_diagnostic_read(self):
        called=[];monitor=MideaFaultMonitor()
        monitor.refresh([ENTITY,'climate.pac_zone_2'],registry,lambda value:called.append(value)or diagnostic())
        self.assertEqual(called,[ENTRY]);self.assertEqual(monitor.snapshot('climate.pac_zone_2')['pac_fault_status'],'reported')
    def test_scheduling_is_bounded_and_does_not_read_on_heartbeat_thread(self):
        monitor=MideaFaultMonitor();reads=[]
        with patch('agent_123_domotique.midea_faults.threading.Thread')as worker:
            monitor.request_refresh([ENTITY,'switch.bad','climate.bad/path'],lambda _:reads.append('registry'),lambda _:reads.append('diagnostic'))
            monitor.request_refresh([ENTITY],lambda _:None,lambda _:None)
            self.assertEqual(reads,[]);worker.assert_called_once();worker.return_value.start.assert_called_once()
            self.assertEqual(worker.call_args.kwargs['args'][0],[ENTITY])
    def test_thread_resource_failure_cannot_break_the_heartbeat(self):
        monitor=MideaFaultMonitor()
        with patch('agent_123_domotique.midea_faults.threading.Thread')as worker:
            worker.return_value.start.side_effect=RuntimeError('busy')
            monitor.request_refresh([ENTITY],registry,lambda _:diagnostic())
        self.assertFalse(monitor.running)
