"""Verify the assembled add-on, without HA, network or writable persistent data."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'package-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Package file missing or changed: ' + name)
    modules = []
    for path in sorted(root.glob('*.py')):
        ast.parse(path.read_text())
        if path.stem != 'release_smoke':
            importlib.import_module(path.stem)
            modules.append(path.stem)
    from agent import AGENT_VERSION
    version = re.search(r'^version: "([^"]+)"', (root / 'config.yaml').read_text(), re.M).group(1)
    if AGENT_VERSION != version or version != manifest['version']:
        raise RuntimeError('Runtime/package version mismatch')
    subprocess.run(['python3', '-m', 'pip', 'check'], check=True)
    print(json.dumps({'passed': True, 'version': version, 'verifiedFiles': len(manifest['files']),
                      'importedModules': modules, 'networkRequired': False}))


if __name__ == '__main__':
    main()
