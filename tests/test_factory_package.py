import ast
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'agent_123_domotique'

class FactoryPackageTests(unittest.TestCase):
    def test_installed_image_contains_importable_factory_modules(self):
        copies = re.findall(r'^COPY (\S+\.py) /opt/agent/\S+', (ROOT / 'Dockerfile').read_text(), re.M)
        with tempfile.TemporaryDirectory() as directory:
            for name in copies:
                shutil.copyfile(ROOT / name, pathlib.Path(directory) / name)
            subprocess.run([sys.executable, '-I', '-c',
                'import sys;sys.path.insert(0,sys.argv[1]);import factory_activation,factory_stage', directory],
                check=True, capture_output=True)

    def test_factory_options_allow_empty_legacy_enrollment_code(self):
        schema = re.search(r'enrollment_code: "match\(([^\n]+)\)"', (ROOT / 'config.yaml').read_text()).group(1)
        self.assertIsNotNone(re.fullmatch(schema, ''))
        self.assertIsNotNone(re.fullmatch(schema, 'ABCD2345'))
        for invalid in ('123', 'lowercas', ' ABCD2345', 'ABCDEFGHI'):
            self.assertIsNone(re.fullmatch(schema, invalid))

    def test_runtime_version_matches_installable_version(self):
        assignments = [node for node in ast.parse((ROOT / 'agent.py').read_text()).body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'AGENT_VERSION' for t in node.targets)]
        actual = ast.literal_eval(assignments[0].value)
        expected = re.search(r'^version: "([^"]+)"', (ROOT / 'config.yaml').read_text(), re.M).group(1)
        self.assertEqual(actual, expected)

if __name__ == '__main__':
    unittest.main()
