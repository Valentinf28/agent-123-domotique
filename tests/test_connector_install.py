import importlib.util
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('connector_install', Path(__file__).parents[1] / 'agent_123_domotique/connector_install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class ConnectorInstallTests(unittest.TestCase):
    def test_official_bundle_installs_offline_and_retry_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)
            unrelated = config / 'configuration.yaml'
            unrelated.write_text('do not modify')
            result = installer.install_solarman(config)
            self.assertEqual(result['status'], 'installed')
            self.assertFalse(result['configured'])
            self.assertTrue(result['restartRequired'])
            root = config / 'custom_components/solarman'
            self.assertTrue((root / 'inverter_definitions/deye_p3.yaml').is_file())
            self.assertTrue((root / 'LICENSE-123HOME-BUNDLE').is_file())
            (root / 'user-customization').write_text('keep')
            self.assertEqual(installer.install_solarman(config)['status'], 'existing_preserved')
            self.assertEqual((root / 'user-customization').read_text(),'keep')
            self.assertEqual(unrelated.read_text(),'do not modify')

    def test_existing_connector_even_incomplete_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'custom_components/solarman'
            root.mkdir(parents=True)
            (root / 'manifest.json').write_text('{"version":"different"}')
            self.assertEqual(installer.install_solarman(folder)['status'], 'existing_preserved')
            self.assertEqual(list(root.iterdir()), [root / 'manifest.json'])

    def test_corrupt_bundle_leaves_no_connector(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'bad.zip'
            bundle.write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError,'altéré'):
                installer.install_solarman(folder,bundle)
            self.assertFalse((Path(folder)/'custom_components/solarman').exists())

    def test_parallel_requests_only_install_once(self):
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(2) as workers:
            results = list(workers.map(lambda _: installer.install_solarman(folder),range(2)))
            self.assertEqual(sorted(r['status'] for r in results), ['existing_preserved','installed'])

    def test_copy_failure_leaves_no_partial_connector_and_retry_works(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(installer.shutil,'copyfile',side_effect=OSError('storage failure')):
                with self.assertRaises(OSError): installer.install_solarman(folder)
            self.assertEqual(list((Path(folder)/'custom_components').iterdir()),[])
            self.assertEqual(installer.install_solarman(folder)['status'],'installed')

    def test_symlinked_configuration_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            external = root/'external'; external.mkdir()
            (root/'custom_components').symlink_to(external, target_is_directory=True)
            with self.assertRaises(RuntimeError): installer.install_solarman(root)
            self.assertEqual(list(external.iterdir()),[])

if __name__ == '__main__': unittest.main()
