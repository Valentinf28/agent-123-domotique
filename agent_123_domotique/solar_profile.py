"""Small, reproducible adaptations to the pinned upstream connector."""
from pathlib import Path
import hashlib

PROFILE = 'deye_sg01hp3_readonly.yaml'
PROFILE_SHA = 'eeb4983bd4d5b3dfdb22acabfec4efe263e1fe66c70088bd44d1bcd222e9e26b'
LP1_PROFILE = 'deye_lp1_readonly.yaml'
LP1_PROFILE_SHA = '19579d03cc63815d3a91cbba513b8c792582a17e3ee344ee618a321595406bad'

MICRO_PROFILE = 'deye_micro_readonly.yaml'
MICRO_PROFILE_SHA = '1829bb97fe167474a75ace476c49487fcf3d9558d5bdd9246a2ca9395661e6fb'
LEGACY_MICRO_PROFILE_SHA = '54cd372ee2d7f9f89c5869934aec702ab87bc50181277cf581093391ee75236c'

def ensure_profile(root, name):
    """Install only a pinned measurement profile in our managed connector."""
    expected = {PROFILE: PROFILE_SHA, LP1_PROFILE: LP1_PROFILE_SHA, MICRO_PROFILE: MICRO_PROFILE_SHA}.get(name)
    if not expected:
        raise RuntimeError('Profil solaire inconnu.')
    root = Path(root)
    target = root / 'inverter_definitions/custom'
    if root.is_symlink() or (root/'inverter_definitions').is_symlink() or target.is_symlink():
        raise RuntimeError('Le dossier du profil solaire doit être vérifié.')
    source = Path(__file__).parent / 'profiles' / name
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError('Profil de mesure solaire altéré.')
    target.mkdir(exist_ok=True)
    destination = target/name
    if destination.is_symlink():
        raise RuntimeError('Un profil solaire différent existe déjà ; il a été conservé.')
    if destination.exists() and destination.read_bytes() != data:
        if name != MICRO_PROFILE or hashlib.sha256(destination.read_bytes()).hexdigest() != LEGACY_MICRO_PROFILE_SHA:
            raise RuntimeError('Un profil solaire différent existe déjà ; il a été conservé.')
        import os, tempfile
        fd, temporary = tempfile.mkstemp(prefix='.123home-micro-profile-', dir=target)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.chmod(temporary, 0o644); os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    if not destination.exists():
        with destination.open('xb') as output:
            output.write(data)

def adapt_connector(root):
    root = Path(root)
    ensure_profile(root, PROFILE)
    ensure_profile(root, LP1_PROFILE)
    ensure_profile(root, MICRO_PROFILE)
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
