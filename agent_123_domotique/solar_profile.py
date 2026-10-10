"""Small, reproducible adaptations to the pinned upstream connector."""
from pathlib import Path
import hashlib

PROFILE = 'deye_sg01hp3_readonly.yaml'
PROFILE_SHA = 'eeb4983bd4d5b3dfdb22acabfec4efe263e1fe66c70088bd44d1bcd222e9e26b'

def adapt_connector(root):
    root = Path(root)
    profile = Path(__file__).parent / 'profiles' / PROFILE
    data = profile.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROFILE_SHA:
        raise RuntimeError('Profil de mesure solaire altéré.')
    target = root / 'inverter_definitions/custom'
    target.mkdir(exist_ok=True)
    (target / PROFILE).write_bytes(data)
    changes = {
        'config_flow.py': [('CONFIGURATION_SCHEMA = {', 'CONFIGURATION_SCHEMA = {\n    vol.Optional("logger_serial"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4294967295)),')],
        'provider.py': [('    async def discover(self):\n', '    async def discover(self):\n        # 1.2.3 Home: explicit logger identity; no logger HTTP reconfiguration.\n        if serial := self.config._options.get("logger_serial"):\n            self.serial = int(serial)\n            return\n')],
    }
    for name, replacements in changes.items():
        path = root / name
        content = path.read_text()
        for old, new in replacements:
            if content.count(old) != 1:
                raise RuntimeError('Version du connecteur incompatible avec la préparation.')
            content = content.replace(old,new,1)
        path.write_text(content)
    (root / '123home-bundle.json').write_text('{"revision":1,"profile":"' + PROFILE + '"}')
