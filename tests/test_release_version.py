"""The portal must receive the version actually offered by the add-on store."""
import ast
from pathlib import Path
import re
import unittest


class ReleaseVersionTests(unittest.TestCase):
    def test_announced_version_matches_installable_package(self):
        addon = Path(__file__).parents[1] / 'agent_123_domotique'
        tree = ast.parse((addon / 'agent.py').read_text())
        versions = [ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'AGENT_VERSION'
                            for target in node.targets)]
        package = re.search(r'^version:\s*"([^"]+)"\s*$',
                            (addon / 'config.yaml').read_text(), re.MULTILINE)
        self.assertIsNotNone(package)
        self.assertEqual(versions, [package.group(1)])


if __name__ == '__main__':
    unittest.main()
