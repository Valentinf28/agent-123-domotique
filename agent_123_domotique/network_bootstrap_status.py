"""Non-secret, fail-closed handoff to the optional first-boot Wi-Fi app."""
import hashlib
import json
import os
from pathlib import Path
from factory_activation import configured

PATH = '/homeassistant_config/.labox-network-bootstrap.json'

def _publish(options, state, path=PATH):
    prepared = configured(options) if not state.get('token') else False
    context = hashlib.sha256(options.get('factory_id', '').encode()).hexdigest()
    value = {'version': 1, 'factoryContext': context, 'prepared': prepared,
             'installed': bool(state.get('token') or options.get('relay_token') or options.get('enrollment_code'))}
    target = Path(path)
    previous = json.loads(target.read_text()) if target.exists() else {}
    if previous.get('factoryContext') == context and previous.get('installed') is True:
        value['installed'] = True
        value['prepared'] = False
    if previous == value:
        os.utime(target, None)
        return
    temporary = target.with_suffix('.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o644)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, target)


def publish(options, state, path=PATH):
    # Optional onboarding must never interrupt normal telemetry or physical control.
    try:
        _publish(options, state, path)
        return True
    except (OSError, ValueError, TypeError):
        return False
