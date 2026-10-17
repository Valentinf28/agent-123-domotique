import importlib.util
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import ast
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import tempfile
import sys
sys.path.append(str(Path(__file__).parents[1] / "agent_123_domotique"))
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
            self.assertEqual(installer.install_solarman(config)['status'], 'installed')
            self.assertEqual((root / 'user-customization').read_text(),'keep')
            self.assertEqual(unrelated.read_text(),'do not modify')

    def test_managed_revision_distinguishes_cached_upstream_and_migrates_idempotently(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertRegex(installer.MANAGED_VERSION,r'^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\+labox\.[1-9][0-9]*$')
            config=Path(folder);installer.install_solarman(config);root=config/'custom_components/solarman'
            manifest=json.loads((root/'manifest.json').read_text());self.assertEqual(manifest['version'],installer.MANAGED_VERSION)
            # Prior managed revision had the same public upstream version while HA kept old code.
            manifest['version']=installer.VERSION;(root/'manifest.json').write_text(json.dumps(manifest))
            (root/'123home-bundle.json').write_text(json.dumps({'revision':1,'profile':'deye_sg01hp3_readonly.yaml'}))
            before=(root/'config_flow.py').read_bytes();installer.install_solarman(config)
            self.assertEqual(json.loads((root/'manifest.json').read_text())['version'],installer.MANAGED_VERSION)
            self.assertEqual((root/'config_flow.py').read_bytes(),before)
            installer.install_solarman(config);self.assertEqual((root/'config_flow.py').read_text().count('vol.Optional("logger_serial")'),1)

    def test_explicit_logger_serial_skips_upstream_network_reconfiguration(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install_solarman(folder)
            root = Path(folder) / 'custom_components/solarman'
            tree = ast.parse((root / 'provider.py').read_text())
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'EndPointProvider')
            method = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'discover')
            namespace = {'request': Mock(side_effect=AssertionError('Logger network must not be changed'))}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])), 'provider.py', 'exec'), namespace)
            endpoint = SimpleNamespace(config=SimpleNamespace(_options={'logger_serial':2974839220}),serial=0)
            asyncio.run(namespace['discover'](endpoint))
            self.assertEqual(endpoint.serial,2974839220)
            namespace['request'].assert_not_called()
            self.assertTrue((root / 'inverter_definitions/custom/deye_sg01hp3_readonly.yaml').is_file())

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
            self.assertEqual(sorted(r['status'] for r in results), ['installed','installed'])

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

class UnusedConnectorMigrationTests(unittest.TestCase):
    def fixture(self, folder, entries):
        config=Path(folder);root=config/'custom_components/solarman';root.mkdir(parents=True)
        (root/'manifest.json').write_text('{"domain":"solarman","version":"legacy"}')
        (root/'custom-file').write_text('retained original')
        storage=config/'.storage';storage.mkdir();(storage/'core.config_entries').write_text(json.dumps({'data':{'entries':entries}}))
        return config,root
    def test_unused_legacy_tree_is_retained_outside_loader_before_install(self):
        with tempfile.TemporaryDirectory() as folder:
            config,root=self.fixture(folder,[{'domain':'tuya'}]);before=(config/'.storage/core.config_entries').read_bytes()
            self.assertEqual(installer.install_solarman(config)['status'],'installed')
            self.assertTrue((root/'123home-bundle.json').is_file())
            backups=list((config/'.labox-connector-backups').iterdir());self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'custom-file').read_text(),'retained original')
            self.assertEqual((config/'.storage/core.config_entries').read_bytes(),before)
            installer.install_solarman(config);self.assertEqual(len(list((config/'.labox-connector-backups').iterdir())),1)
    def test_active_connection_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            config,root=self.fixture(folder,[{'domain':'solarman','entry_id':'real'}])
            self.assertEqual(installer.install_solarman(config)['status'],'existing_preserved')
            self.assertEqual((root/'custom-file').read_text(),'retained original');self.assertFalse((config/'.labox-connector-backups').exists())
    def test_corrupt_candidate_preserves_the_entire_original(self):
        with tempfile.TemporaryDirectory() as folder:
            config,root=self.fixture(folder,[]);bundle=config/'broken.zip';bundle.write_bytes(b'broken')
            with self.assertRaises(RuntimeError):installer.install_solarman(config,bundle)
            self.assertEqual((root/'custom-file').read_text(),'retained original');self.assertFalse((config/'.labox-connector-backups').exists())
    def test_new_connection_during_migration_restores_original_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            config,root=self.fixture(folder,[])
            with patch.object(installer,'unused_connector',side_effect=[True,True,False]):
                with self.assertRaisesRegex(RuntimeError,'ajoutée'):installer.install_solarman(config)
            self.assertEqual((root/'custom-file').read_text(),'retained original');self.assertFalse((root/'123home-bundle.json').exists())
    def test_symlinked_backup_directory_is_refused_without_touching_original(self):
        with tempfile.TemporaryDirectory() as folder:
            config,root=self.fixture(folder,[]);external=config/'external';external.mkdir();(config/'.labox-connector-backups').symlink_to(external,target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError,'sauvegarde'):installer.install_solarman(config)
            self.assertEqual((root/'custom-file').read_text(),'retained original');self.assertEqual(list(external.iterdir()),[])

if __name__ == '__main__': unittest.main()
