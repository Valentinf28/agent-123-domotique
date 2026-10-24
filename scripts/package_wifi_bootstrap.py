"""Hash every delivered first-boot app source; fail on an omitted runtime file."""
import argparse
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1] / 'labox_wifi_bootstrap'
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*'))
       if p.is_file() and '__pycache__' not in p.parts and p.name not in ('manifest.json',) and not p.name.endswith('.pyc')}
encoded=json.dumps({'version':'0.1.1','files':files},indent=2,sort_keys=True)+'\n'
if args.check:
    assert (root/'manifest.json').read_text()==encoded, 'Stale first-boot manifest'
else:(root/'manifest.json').write_text(encoded)
print('First-boot manifest verified:',len(files),'files')
