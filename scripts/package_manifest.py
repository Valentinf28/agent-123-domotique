"""Generate or check the manifest of every source file copied into the add-on."""
import argparse
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / 'agent_123_domotique'
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
files = {}
copied = set()
for source, destination in re.findall(r'^COPY (\S+) (\S+)\s*$', (root / 'Dockerfile').read_text(), re.M):
    if source == 'package-manifest.json':
        continue
    path = root / source
    if not path.exists():
        raise SystemExit('Missing Docker COPY source: ' + source)
    if destination.startswith('/opt/agent/'):
        if path.is_dir():
            for child in sorted(path.rglob('*')):
                if child.is_file() and '__pycache__' not in child.parts:
                    relative = str(Path(destination.removeprefix('/opt/agent/')) / child.relative_to(path))
                    files[relative] = hashlib.sha256(child.read_bytes()).hexdigest()
        else:
            relative = destination.removeprefix('/opt/agent/')
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            copied.add(source)
missing = {p.name for p in root.glob('*.py') if not p.name.startswith('test_')} - copied
if missing:
    raise SystemExit('Python modules absent from image: ' + ', '.join(sorted(missing)))
version = re.search(r'^version: "([^"]+)"', (root / 'config.yaml').read_text(), re.M).group(1)
encoded = json.dumps({'version': version, 'files': files}, indent=2, sort_keys=True) + '\n'
manifest = root / 'package-manifest.json'
if args.check:
    if not manifest.exists() or manifest.read_text() != encoded:
        raise SystemExit('Package manifest is stale; regenerate before publishing')
else:
    manifest.write_text(encoded)
print('Package manifest verified:', len(files), 'files, version', version)
