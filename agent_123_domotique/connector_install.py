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

VERSION = "25.08.16"
DIGEST = "04fd37da1ba1cd3a590146a48602162ad5c7e0c319c80ca326369cd5a26da977"
BUNDLE = Path(__file__).parent / "vendor" / f"solarman-{VERSION}.zip"
CONFIG = Path("/homeassistant_config")


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
        if destination.exists() or destination.is_symlink():
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
            shutil.copyfile(bundle.parent / "SOLARMAN-LICENSE", temporary / "LICENSE-123HOME-BUNDLE")
            # Destination is absent and staging is on the same filesystem.
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return {"connector": "solarman", "status": "installed", "version": VERSION,
                "restartRequired": True, "configured": False}
