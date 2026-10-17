"""Small, reproducible adaptations to the pinned upstream connector."""
from pathlib import Path
import hashlib

PROFILE = 'deye_sg01hp3_readonly.yaml'
PROFILE_SHA = 'eeb4983bd4d5b3dfdb22acabfec4efe263e1fe66c70088bd44d1bcd222e9e26b'
LP1_PROFILE = 'deye_lp1_readonly.yaml'
LP1_PROFILE_SHA = 'c972255606fc6f876b2b66f20d163872cc4121e2bfcf456f712302a679d7418d'
LEGACY_LP1_PROFILE_SHA = '19579d03cc63815d3a91cbba513b8c792582a17e3ee344ee618a321595406bad'

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
        legacy = {MICRO_PROFILE: LEGACY_MICRO_PROFILE_SHA, LP1_PROFILE: LEGACY_LP1_PROFILE_SHA}
        if hashlib.sha256(destination.read_bytes()).hexdigest() != legacy.get(name):
            raise RuntimeError('Un profil solaire différent existe déjà ; il a été conservé.')
        import os, tempfile
        if name == LP1_PROFILE:
            import json
            marker=target/'.123home-lp1-cadence.json'
            if marker.is_symlink():raise RuntimeError('Le suivi du profil solaire doit être vérifié.')
            mfd, pending_marker=tempfile.mkstemp(prefix='.123home-cadence-',dir=target)
            try:
                with os.fdopen(mfd,'w') as output:
                    json.dump({'sha256':expected},output);output.flush();os.fsync(output.fileno())
                os.chmod(pending_marker,0o644);os.replace(pending_marker,marker)
            finally:
                if os.path.exists(pending_marker):os.unlink(pending_marker)
        fd, temporary = tempfile.mkstemp(prefix='.123home-measurement-profile-', dir=target)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.chmod(temporary, 0o644); os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    if not destination.exists():
        with destination.open('xb') as output:
            output.write(data)

def qualify_managed_connector(root):
    """Distinct loaded version proves HA has discarded the unadapted module cache."""
    import json, os, tempfile
    from connector_install import MANAGED_VERSION, MANAGED_PRIOR_VERSIONS
    root = Path(root)
    paths = [root / name for name in ('manifest.json', 'config_flow.py', 'provider.py', '123home-bundle.json')]
    if root.is_symlink() or any(path.is_symlink() for path in paths):
        raise RuntimeError('Le connecteur solaire doit être vérifié avant activation.')
    if (root/'config_flow.py').read_text().count('vol.Optional("logger_serial")') != 1 or 'if serial := self.config._options.get("logger_serial"):' not in (root/'provider.py').read_text():
        raise RuntimeError('La préparation du connecteur solaire est incomplète.')
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest.get('domain') != 'solarman' or manifest.get('version') not in MANAGED_PRIOR_VERSIONS:
        raise RuntimeError('La version du connecteur solaire doit être vérifiée.')
    manifest['version'] = MANAGED_VERSION
    for name, value in [('manifest.json', manifest), ('123home-bundle.json', {'revision':2,'profile':PROFILE})]:
        target=root/name
        if target.is_file() and json.loads(target.read_text()) == value:
            continue
        fd, temporary = tempfile.mkstemp(prefix='.123home-metadata-', dir=root)
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(value, output); output.flush(); os.fsync(output.fileno())
            os.chmod(temporary, 0o644); os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


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
    qualify_managed_connector(root)
