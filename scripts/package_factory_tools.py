"""Manifest for both separately packaged workshop/maintenance apps."""
import argparse,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
for name in ('labox_boot_prepare','labox_maintenance'):
    folder=root/name
    files={str(x.relative_to(folder)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(folder.rglob('*')) if x.is_file() and '__pycache__' not in x.parts and x.name!='manifest.json' and not x.name.endswith('.pyc')}
    encoded=json.dumps({'files':files},sort_keys=True,indent=2)+'\n';target=folder/'manifest.json'
    if args.check:assert target.read_text()==encoded, name+' stale manifest'
    else:target.write_text(encoded)
    print(name,len(files),'files verified')
