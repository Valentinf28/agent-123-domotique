"""Activate the bundled connector, with a persisted restart cooldown."""
import fcntl
import json
import os
from pathlib import Path
import time
import urllib.error


def activate(call, *, config=Path('/homeassistant_config'), data=Path('/data'), now=None):
    now = time.time() if now is None else now
    config, data = Path(config), Path(data)
    if not (config / 'custom_components/solarman/123home-bundle.json').is_file():
        raise RuntimeError('Préparez le connecteur guidé avant son activation. Le connecteur existant est conservé.')
    data.mkdir(exist_ok=True)
    descriptor = os.open(data / 'solar-activation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor,'w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        handlers = call('/config/config_entries/flow_handlers')
        if not isinstance(handlers,list):
            raise RuntimeError('La box ne peut pas vérifier les connecteurs disponibles.')
        if 'solarman' in handlers:
            return {'connector':'solarman','status':'ready','configured':False}
        journal = data / 'solar-activation.json'
        state = json.loads(journal.read_text()) if journal.exists() else {}
        requested = state.get('requestedAt')
        if isinstance(requested,(float,int)) and now-requested < 300:
            return {'connector':'solarman','status':'activation_pending','configured':False}
        temporary = journal.with_suffix('.tmp')
        temporary.write_text(json.dumps({'requestedAt':now}))
        temporary.chmod(0o600)
        temporary.replace(journal)
        try:
            call('/services/homeassistant/restart',method='POST',payload={},timeout=15)
        except urllib.error.HTTPError:
            # Explicit refusal is not a successful restart request.
            journal.unlink(missing_ok=True)
            raise RuntimeError('Le redémarrage du service a été refusé par la box.') from None
        except (TimeoutError, urllib.error.URLError, ConnectionError):
            # The response can be lost during restart. Never immediately replay it.
            pass
        return {'connector':'solarman','status':'activation_pending','configured':False}
