"""Import and integrity smoke check for the assembled optional app, no host bus needed."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

def main():
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root))
    manifest = json.loads((root / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    for module in ('model', 'network', 'access_point', 'controller', 'http_setup', 'workshop', 'preflight', 'service'):
        importlib.import_module(module)
    from network import profile
    from dbus_fast import Message
    encoded = Message(destination='org.freedesktop.NetworkManager', path='/org/freedesktop/NetworkManager/Settings',
        interface='org.freedesktop.NetworkManager.Settings', member='AddConnection2', signature='a{sa{sv}}ua{sv}',
        body=[profile('00000000-0000-4000-8000-000000000001', '00:11:22:33:44:55', 'fixture-only', 'fixture-only-password', hotspot=True), 2, {}])
    assert len(encoded._marshall(False)) > 500
    print(json.dumps({'passed': True, 'files': len(manifest['files']), 'dbusMessageEncoded': True, 'hostNetworkChanged': False}))

if __name__ == '__main__': main()
