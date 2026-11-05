from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from ddzy422_setup import install, DOMAIN
from ddzy422_diagnostics import diagnose

NOW = datetime(2026, 11, 5, 22, 0, tzinfo=timezone.utc)
ADAPTERS = [{'enabled': True, 'ipv4': [{'address': '192.168.1.10', 'network_prefix': 24}]}]
SETTINGS = {'host': '192.168.1.123', 'logger_serial': 1234567890, 'mac': '020000000001'}


class MeterDiagnosticTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        install(self.root)
        (self.root/'.storage').mkdir()
        (self.root/'.storage/core.config_entries').write_text(json.dumps({'data': {'entries': [
            {'entry_id': 'selected', 'domain': DOMAIN, 'data': SETTINGS},
            {'entry_id': 'other', 'domain': DOMAIN, 'data': {**SETTINGS, 'logger_serial': 123}},
        ]}}))
        self.call = Mock(return_value=[{'entry_id': 'selected', 'state': 'setup_retry'},
                                      {'entry_id': 'other', 'state': 'loaded'}])
        self.reader = Mock(return_value={'readAtUtc': NOW.isoformat(), 'values': {
            'gridPowerW': -200, 'importTotalKwh': 100, 'exportTotalKwh': 20}})
        self.checkpoint = self.root/f'.storage/{DOMAIN}.{SETTINGS["logger_serial"]}.indexes'

    def run_diagnostic(self, **kwargs):
        return diagnose('selected', ADAPTERS, self.call, config=self.root, reader=self.reader, **kwargs)

    def write_checkpoint(self, **kwargs):
        value = {'importTotalKwh': 99.99, 'exportTotalKwh': 20, 'at': NOW.timestamp()-10, **kwargs}
        self.checkpoint.write_text(json.dumps({'version': 1, 'data': value}))
        return self.checkpoint.read_bytes()

    def test_verified_probe_does_not_claim_native_recovery_or_write_checkpoint(self):
        before = self.write_checkpoint()
        result = self.run_diagnostic()
        self.assertTrue(result['hardwareReadVerified'])
        self.assertTrue(result['continuityVerified'])
        self.assertFalse(result['readingsAvailable'])
        self.assertFalse(result['checkpointWritten'])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.reader.assert_called_once_with(SETTINGS)
        self.call.assert_called_once_with('/config/config_entries/entry?domain='+DOMAIN)

    def test_missing_checkpoint_stays_missing(self):
        self.assertTrue(self.run_diagnostic()['continuityVerified'])
        self.assertFalse(self.checkpoint.exists())

    def test_decreased_indexes_are_classified_and_preserved(self):
        before = self.write_checkpoint(exportTotalKwh=20.05)
        result = self.run_diagnostic()
        self.assertTrue(result['hardwareReadVerified'])
        self.assertEqual(result['reason'], 'index_decreased')
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_clock_backwards_and_jump_are_not_transport_faults(self):
        for settings, reason in [({'at': NOW.timestamp()+1}, 'clock_backwards'),
                                 ({'importTotalKwh': 90}, 'index_jump')]:
            self.write_checkpoint(**settings)
            self.assertEqual(self.run_diagnostic()['reason'], reason)

    def test_read_failure_never_leaks_exception_or_fabricates_zero(self):
        for message, reason in [('Meter discovery handshake did not answer', 'discovery_timeout'),
                                ('No valid CRC-checked measurement block', 'measurement_timeout'),
                                ('secret-error-details', 'read_unverified')]:
            self.reader.side_effect = TimeoutError(message)
            result = self.run_diagnostic()
            self.assertFalse(result['hardwareReadVerified'])
            self.assertEqual(result['reason'], reason)
            self.assertNotIn('measurements', result)
            self.assertNotIn(message, json.dumps(result))

    def test_no_probe_while_normal_reader_or_setup_is_active(self):
        for state in ['loaded', 'setup_in_progress', 'not_loaded']:
            self.call.return_value = [{'entry_id': 'selected', 'state': state}]
            with self.assertRaises(RuntimeError):
                self.run_diagnostic()
        self.reader.assert_not_called()

    def test_unknown_entry_and_tampered_bundle_are_not_probed(self):
        with self.assertRaises(RuntimeError):
            diagnose('absent', ADAPTERS, self.call, config=self.root, reader=self.reader)
        (self.root/'custom_components'/DOMAIN/'transport.py').write_text('changed')
        with self.assertRaises(RuntimeError):
            self.run_diagnostic()
        self.reader.assert_not_called()

    def test_wrong_network_does_not_open_reader(self):
        result = diagnose('selected', [], self.call, config=self.root, reader=self.reader)
        self.assertEqual(result['reason'], 'wrong_network')
        self.reader.assert_not_called()

    def test_symlink_or_invalid_checkpoint_never_rebased(self):
        self.checkpoint.write_text('{"data": "invalid"}')
        before = self.checkpoint.read_bytes()
        self.assertEqual(self.run_diagnostic()['reason'], 'invalid_checkpoint')
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.checkpoint.unlink()
        external = self.root/'external'
        external.write_text('private-data')
        self.checkpoint.symlink_to(external)
        self.assertEqual(self.run_diagnostic()['reason'], 'invalid_checkpoint')
        self.assertEqual(external.read_text(), 'private-data')


if __name__ == '__main__':
    unittest.main()
