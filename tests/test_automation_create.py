import copy
import tempfile
import unittest
import urllib.error
from pathlib import Path
from automation_edit import create


class AutomationCreateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.config = None
        self.writes = []
        self.reloads = 0
        self.zone = 'Europe/Paris'
        self.missing_entity = False
        self.fail_reload = False
        self.external_change = False
        self.target_state = 'off'
        self.payload = dict(name='Filtration matin', triggerType='time', time='08:30',
                            weekdays=['fri', 'mon'], entityId='switch.filtration',
                            domain='switch', service='turn_on', timeZone=self.zone)

    def call(self, path, method='GET', payload=None):
        if path == '/config':
            return {'time_zone': self.zone}
        if path == '/states/switch.filtration':
            return {'entity_id': 'switch.filtration', 'state': self.target_state}
        if path == '/states':
            if self.missing_entity:
                return []
            return [{'entity_id': 'automation.actual_native_identity', 'state': 'on',
                     'attributes': {'id': self.config['id']}}]
        if path == '/services/automation/reload':
            self.reloads += 1
            if self.external_change and self.reloads == 1:
                self.config['alias'] = 'External edit'
            if self.fail_reload and self.reloads == 1:
                raise TimeoutError('fixture timeout')
            return []
        self.assertTrue(path.startswith('/config/automation/config/'))
        if method == 'GET':
            if self.config is None:
                raise urllib.error.HTTPError(path, 404, 'missing', {}, None)
            return copy.deepcopy(self.config)
        self.writes.append(method)
        if method == 'POST':
            self.config = copy.deepcopy(payload)
        elif method == 'DELETE':
            self.config = None
        else:
            self.fail('Unexpected write')
        return {}

    def execute(self, changes=None):
        return create(self.payload | (changes or {}), self.call,
                      operation_id='create-test-1', data=self.data, clock=lambda: 1792866600)

    def test_weekdays_are_native_and_real_identity_is_returned(self):
        result = self.execute()
        self.assertEqual(result['entityId'], 'automation.actual_native_identity')
        self.assertTrue(result['created'])
        self.assertEqual(self.config['trigger'], [{'platform': 'time', 'at': '08:30:00'}])
        self.assertEqual(self.config['condition'], [{'condition': 'time', 'weekday': ['mon', 'fri']}])
        self.assertEqual(self.config['action'], [{'service': 'switch.turn_on', 'target': {'entity_id': 'switch.filtration'}}])
        self.assertEqual(next((self.data / 'automation-edits').glob('*.json')).stat().st_mode & 0o777, 0o600)

    def test_daily_has_no_weekday_filter_or_utc_conversion(self):
        self.execute({'weekdays': [], 'time': '02:30'})
        self.assertEqual(self.config['condition'], [])
        self.assertEqual(self.config['trigger'][0]['at'], '02:30:00')

    def test_sunrise_and_sunset_are_native_events(self):
        for event in ('sunrise', 'sunset'):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                self.data = Path(directory)
                self.config = None
                self.execute({'triggerType': event, 'time': None})
                self.assertEqual(self.config['trigger'], [{'platform': 'sun', 'event': event}])

    def test_timezone_mismatch_and_invalid_zone_refuse_before_write(self):
        for zone in ('UTC', 'not/a-zone'):
            with self.subTest(zone=zone), self.assertRaises((ValueError, RuntimeError)):
                self.execute({'timeZone': zone})
        self.assertEqual(self.writes, [])

    def test_invalid_schedule_and_unavailable_target_refuse_before_write(self):
        for changes in ({'time': '25:00'}, {'weekdays': ['mon', 'mon']}, {'name': 'x'},
                        {'triggerType': 'sunset', 'time': '12:00'}, {'service': 'toggle'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.execute(changes)
        self.target_state = 'unavailable'
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_repeated_request_does_not_create_or_reload_again(self):
        first = self.execute()
        self.assertEqual(self.execute(), first)
        self.assertEqual(self.writes, ['POST'])
        self.assertEqual(self.reloads, 1)

    def test_missing_native_identity_rolls_back_only_new_configuration(self):
        self.missing_entity = True
        with self.assertRaisesRegex(RuntimeError, 'Aucune nouvelle règle conservée'):
            self.execute()
        self.assertIsNone(self.config)
        self.assertEqual(self.writes, ['POST', 'DELETE'])

    def test_uncertain_reload_does_not_retry_create_and_rolls_back(self):
        self.fail_reload = True
        with self.assertRaises(RuntimeError):
            self.execute()
        with self.assertRaisesRegex(RuntimeError, 'aucun doublon'):
            self.execute()
        self.assertEqual(self.writes, ['POST', 'DELETE'])

    def test_external_edit_never_deleted_by_rollback(self):
        self.external_change = True
        with self.assertRaisesRegex(RuntimeError, 'opérateur'):
            self.execute()
        self.assertEqual(self.config['alias'], 'External edit')
        self.assertEqual(self.writes, ['POST'])

if __name__ == '__main__':
    unittest.main()
