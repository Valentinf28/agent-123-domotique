"""Verify built app content and encode the privileged call offline; never uses a host bus."""
import hashlib,importlib,json
from pathlib import Path
import sys

name=sys.argv[1];proof=Path('/opt/proof');manifest=json.loads((proof/'manifest.json').read_text())
base=Path('/opt/boot' if name=='labox_boot_prepare' else '/opt/maintenance');sys.path.insert(0,str(base))
for relative,digest in manifest['files'].items():
    path=base/relative if relative.endswith('.py') or relative=='requirements.lock' else proof/relative
    assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,relative
for file in base.glob('*.py'):importlib.import_module(file.stem)
if name=='labox_maintenance':
    from dbus_fast import Message
    from host import properties
    message=Message(destination='org.freedesktop.systemd1',path='/org/freedesktop/systemd1',interface='org.freedesktop.systemd1.Manager',member='StartTransientUnit',signature='ssa(sv)a(sa(sv))',body=['labox-maintenance-session.service','fail',properties(),[]])
    assert len(message._marshall(False))>500
else:
    from boot import target,audit
    assert audit(target(b'console=tty0\n'))['parametersPresent']
print(json.dumps({'passed':True,'module':name,'verifiedFiles':len(manifest['files']),'hostAccess':False}))
