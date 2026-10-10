from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
sys.path.append(str(Path(__file__).parents[1] / 'agent_123_domotique'))
from solar_measurements import inspect_measurements, POWER_NAMES

class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
        self.entries = [{'entry_id': 'ours', 'domain': 'solarman', 'state': 'loaded'}]
        self.registry = []
        self.states = []
        for index, name in enumerate(['Device Serial Number', *POWER_NAMES.values()]):
            entity = f'sensor.renamed_{index}'
            self.registry.append({'entity_id': entity, 'config_entry_id': 'ours',
                                  'platform': 'solarman', 'original_name': name})
            self.states.append({'entity_id': entity, 'state': '2406150574' if index == 0 else '0',
                                'attributes': {'unit_of_measurement': 'W'},
                                'last_reported': self.now.isoformat()})
    def inspect(self):
        return inspect_measurements('ours', '2406150574', self.entries, self.registry,
                                    self.states, now=self.now)
    def test_zero_power_is_valid_but_not_a_physical_test(self):
        result = self.inspect()
        self.assertTrue(result['readingsAvailable'])
        self.assertFalse(result['physicalTestVerified'])
    def test_other_inverter_cannot_fill_missing_measurement(self):
        self.registry[1]['config_entry_id'] = 'other'
        self.assertEqual(self.inspect()['measurements']['production']['status'], 'missing')
    def test_wrong_identity_blocks_readiness(self):
        self.states[0]['state'] = '1234567890'
        self.assertEqual(self.inspect()['identityStatus'], 'mismatch')
        self.assertFalse(self.inspect()['readingsAvailable'])
    def test_unavailable_nan_unknown_units_rejected(self):
        for value, unit in [('unknown', 'W'), ('NaN', 'W'), ('inf', 'W'), ('4', 'Wh')]:
            with self.subTest(value=value, unit=unit):
                self.states[1].update(state=value, attributes={'unit_of_measurement': unit})
                self.assertFalse(self.inspect()['readingsAvailable'])
    def test_old_future_and_absent_reports_rejected(self):
        for stamp in ['2026-10-07T11:56:59+00:00', '2026-10-07T12:01:00+00:00', '', '2026-10-07T12:00:00']:
            with self.subTest(stamp=stamp):
                self.states[1]['last_reported'] = stamp
                self.assertFalse(self.inspect()['readingsAvailable'])
    def test_unchanged_value_recently_reported_and_kw_conversion(self):
        self.states[1].update(state='1.2', last_updated='2020-01-01T00:00:00Z',
                              attributes={'unit_of_measurement': 'kW'})
        self.assertEqual(self.inspect()['measurements']['production']['watts'], 1200)
    def test_ambiguous_entity_rejected(self):
        self.registry.append(dict(self.registry[1]))
        self.assertFalse(self.inspect()['readingsAvailable'])
    def test_unloaded_or_wrong_platform_rejected(self):
        self.entries[0]['state'] = 'setup_retry'
        with self.assertRaises(RuntimeError): self.inspect()
        self.entries[0]['state'] = 'loaded'
        self.registry[1]['platform'] = 'other'
        self.assertFalse(self.inspect()['readingsAvailable'])

    def test_bundled_profile_device_serial_attribute(self):
        self.registry[0]['original_name']='Device'
        self.states[0].update(state='HV 3-Phase Hybrid Inverter', attributes={'Serial Number':'2406150574'})
        self.assertTrue(self.inspect()['readingsAvailable'])
        self.states[0]['attributes']['Serial Number']='other'
        self.assertEqual(self.inspect()['identityStatus'],'mismatch')
        self.registry[0]['config_entry_id']='other'
        self.assertEqual(self.inspect()['identityStatus'],'missing')

    def add_battery_level(self):
        self.registry.append({'entity_id': 'sensor.renamed_soc', 'config_entry_id': 'ours',
                              'platform': 'solarman', 'original_name': 'Battery'})
        self.states.append({'entity_id': 'sensor.renamed_soc', 'state': '94',
                            'attributes': {'unit_of_measurement': '%', 'device_class': 'battery'},
                            'last_reported': self.now.isoformat()})

    def test_battery_percentage_is_optional_and_scoped(self):
        self.assertEqual(self.inspect()['batteryLevel']['status'], 'missing')
        self.assertTrue(self.inspect()['readingsAvailable'])
        self.add_battery_level()
        self.assertEqual(self.inspect()['batteryLevel']['percent'], 94)
        self.registry[-1]['config_entry_id'] = 'other'
        self.assertEqual(self.inspect()['batteryLevel']['status'], 'missing')

    def test_battery_percentage_rejects_invalid_or_old_values(self):
        self.add_battery_level()
        for value in ['unknown', 'NaN', '-1', '101']:
            self.states[-1]['state'] = value
            self.assertEqual(self.inspect()['batteryLevel']['status'], 'unavailable')
        self.states[-1]['state'] = '0'
        self.assertEqual(self.inspect()['batteryLevel']['percent'], 0)
        self.states[-1]['last_reported'] = '2026-10-07T11:00:00+00:00'
        self.assertEqual(self.inspect()['batteryLevel']['status'], 'stale')
        self.states[-1]['attributes']['unit_of_measurement'] = 'W'
        self.assertEqual(self.inspect()['batteryLevel']['status'], 'unavailable')

    def test_duplicate_battery_percentage_is_not_selected(self):
        self.add_battery_level()
        self.registry.append(dict(self.registry[-1]))
        self.assertEqual(self.inspect()['batteryLevel']['status'], 'missing')

if __name__ == '__main__': unittest.main()
