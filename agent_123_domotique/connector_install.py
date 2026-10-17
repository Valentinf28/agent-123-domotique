"""Install the pinned solar connector without HACS or altering existing installs."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile
import fcntl
import uuid

VERSION = "25.08.16"
DIGEST = "04fd37da1ba1cd3a590146a48602162ad5c7e0c319c80ca326369cd5a26da977"
BUNDLE = Path(__file__).parent / "vendor" / f"solarman-{VERSION}.zip"
CONFIG = Path("/homeassistant_config")


def unused_connector(config):
    """An old tree is replaceable only with readable, empty SolarMAN ownership."""
    storage = config / '.storage/core.config_entries'
    if storage.parent.is_symlink() or storage.is_symlink() or not storage.is_file():
        return False
    try:
        entries = json.loads(storage.read_text())['data']['entries']
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return isinstance(entries, list) and all(isinstance(e, dict) and isinstance(e.get('domain'), str) for e in entries) and not any(e['domain'] == 'solarman' for e in entries)


def installed_result():
    return {"connector": "solarman", "status": "installed", "version": VERSION,
            "restartRequired": True, "configured": False}


def install_solarman(config=CONFIG, bundle=BUNDLE):
    """Only writes custom_components/solarman. Does not restart or configure HA."""
    config, bundle = Path(config), Path(bundle)
    if not config.is_dir() or config.is_symlink():
        raise RuntimeError("Le dossier de configuration de la box n’est pas accessible.")
    components = config / "custom_components"
    if components.is_symlink():
        raise RuntimeError("Le dossier des connecteurs doit être vérifié avant installation.")
    components.mkdir(exist_ok=True)
    # Concurrent relay/heartbeat requests must not replace a just-installed tree.
    lock = config / ".123home-solarman-install.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        destination = components / "solarman"
        replace_unused = False
        if destination.exists() or destination.is_symlink():
            marker = destination / "123home-bundle.json"
            if not destination.is_symlink() and marker.is_file() and not marker.is_symlink():
                value = json.loads(marker.read_text())
                manifest = json.loads((destination / "manifest.json").read_text())
                if value == {"revision": 1, "profile": "deye_sg01hp3_readonly.yaml"} and manifest.get("domain") == "solarman" and manifest.get("version") == VERSION:
                    from solar_profile import ensure_profile, PROFILE, LP1_PROFILE, MICRO_PROFILE
                    for profile in (PROFILE, LP1_PROFILE, MICRO_PROFILE):
                        ensure_profile(destination, profile)
                    return installed_result()
            # Preserve every active/ambiguous/custom-managed installation.
            replace_unused = (destination.is_dir() and not destination.is_symlink()
                              and not marker.exists() and not marker.is_symlink() and unused_connector(config))
            if not replace_unused:
                return {"connector": "solarman", "status": "existing_preserved", "configured": False}
        if hashlib.sha256(bundle.read_bytes()).hexdigest() != DIGEST:
            raise RuntimeError("Le connecteur solaire fourni est incomplet ou altéré.")
        temporary = Path(tempfile.mkdtemp(prefix=".123home-solarman-", dir=components))
        try:
            with zipfile.ZipFile(bundle) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 32 * 1024 * 1024:
                    raise RuntimeError("Archive du connecteur trop volumineuse.")
                seen = set()
                for entry in entries:
                    path = PurePosixPath(entry.filename)
                    mode = entry.external_attr >> 16
                    if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                            or stat.S_ISLNK(mode) or path in seen):
                        raise RuntimeError("Archive du connecteur invalide.")
                    seen.add(path)
                    target = temporary.joinpath(*path.parts)
                    if entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(entry) as source, target.open("xb") as output:
                            shutil.copyfileobj(source, output)
                        target.chmod(0o644)
            manifest = json.loads((temporary / "manifest.json").read_text())
            if manifest.get("domain") != "solarman" or manifest.get("version") != VERSION:
                raise RuntimeError("Version du connecteur solaire inattendue.")
            from solar_profile import adapt_connector
            adapt_connector(temporary)
            shutil.copyfile(bundle.parent / "SOLARMAN-LICENSE", temporary / "LICENSE-123HOME-BUNDLE")
            temporary.chmod(0o755)
            if replace_unused:
                # Stage completely first. Retain the entire old tree outside HA's
                # loader path, on the same filesystem, so rollback is an atomic move.
                backups = config / '.labox-connector-backups'
                if backups.is_symlink() or backups.exists() and not backups.is_dir():
                    raise RuntimeError('Le dossier de sauvegarde des connecteurs doit être vérifié.')
                backups.mkdir(mode=0o700, exist_ok=True)
                if not unused_connector(config):
                    raise RuntimeError('Une connexion solaire a été ajoutée pendant la préparation. Elle est conservée.')
                backup = backups / ('solarman-' + uuid.uuid4().hex)
                destination.rename(backup)
                try:
                    if not unused_connector(config):
                        raise RuntimeError('Une connexion solaire a été ajoutée pendant la préparation. Elle est conservée.')
                    temporary.rename(destination)
                except Exception:
                    backup.rename(destination)
                    raise
            else:
                temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return installed_result()
