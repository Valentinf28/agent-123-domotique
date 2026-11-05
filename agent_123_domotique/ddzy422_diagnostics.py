"""Bounded read-only evidence for one managed physical meter.

Never rebase indexes, change native settings, write registers, or expose frames.
"""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re

from ddzy422_setup import BUNDLE, DOMAIN, verify_bundle

REASONS = {
    'Meter discovery handshake did not answer': 'discovery_timeout',
    'Wrong discovery source': 'identity_mismatch',
    'Wrong meter identity': 'identity_mismatch',
    'No valid CRC-checked measurement block': 'measurement_timeout',
    'Meter reader busy': 'reader_busy',
    'Implausible meter values': 'invalid_measurement',
    'Outside this single-phase meter range': 'invalid_measurement',
    'Meter must be on a local network of this box': 'wrong_network',
    'Invalid energy indexes': 'invalid_indexes',
    'Invalid observation time': 'invalid_observation_time',
    'Persisted energy checkpoint invalid': 'invalid_checkpoint',
    'Clock moved backwards': 'clock_backwards',
    'Energy index decreased; explicit maintenance required': 'index_decreased',
    'Energy index jump exceeds single-phase meter range': 'index_jump',
}


def diagnose(entry_id, adapters, call, *, config=Path('/homeassistant_config'),
             reader=None, guard_type=None):
    if not isinstance(entry_id, str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}', entry_id):
        raise ValueError('Connexion du compteur invalide.')
    config = Path(config)
    if config.is_symlink() or (config/'custom_components').is_symlink():
        raise RuntimeError('La configuration du compteur doit être vérifiée.')
    inventory = verify_bundle()
    target = config/'custom_components'/DOMAIN
    import hashlib
    for name, digest in inventory['files'].items():
        path = target/name
        if target.is_symlink() or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Le lecteur du compteur doit correspondre au paquet vérifié.')
    storage = config/'.storage'
    entries_path = storage/'core.config_entries'
    if storage.is_symlink() or entries_path.is_symlink():
        raise RuntimeError('La configuration native doit être vérifiée.')
    entries = json.loads(entries_path.read_text())['data']['entries']
    selected = [e for e in entries if e.get('entry_id') == entry_id and e.get('domain') == DOMAIN]
    if len(selected) != 1 or selected[0].get('disabled_by'):
        raise RuntimeError('Ce compteur actif n’a pas été retrouvé.')
    settings = dict(selected[0]['data'])
    # Load only the immutable packaged read-only transport, never a caller path.
    spec = importlib.util.spec_from_file_location('_labox_ddzy422_diagnostic_transport', BUNDLE/'transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    transport.validate_settings(settings.get('host'), settings.get('logger_serial'), settings.get('mac'))
    live = call('/config/config_entries/entry?domain='+DOMAIN)
    matching = [e for e in live if e.get('entry_id') == entry_id] if isinstance(live, list) else []
    if len(matching) != 1 or matching[0].get('disabled_by'):
        raise RuntimeError('L’état actuel du compteur doit être vérifié.')
    # A separate diagnostic reader must not contend with the normal 5 s reader.
    # Retry states have no active coordinator polling; don't probe during setup.
    if matching[0].get('state') != 'setup_retry':
        raise RuntimeError('Le diagnostic matériel nécessite un compteur en attente de connexion.')
    result = {'entryId': entry_id, 'model': 'ddzy422', 'state': 'setup_retry',
              'hardwareReadVerified': False, 'checkpointWritten': False,
              'readingsAvailable': False, 'reason': None}
    try:
        transport.validate_local_host(settings['host'], adapters)
        sample = (reader or transport.read_sample)(settings)
        at = datetime.fromisoformat(sample['readAtUtc'].replace('Z', '+00:00'))
        if at.tzinfo is None:
            raise ValueError('Invalid observation time')
        values = sample['values']
        result.update(hardwareReadVerified=True, readAtUtc=at.astimezone(timezone.utc).isoformat(),
                      measurements={k: values[k] for k in ('gridPowerW', 'importTotalKwh', 'exportTotalKwh')})
        checkpoint_path = storage/f"{DOMAIN}.{settings['logger_serial']}.indexes"
        if checkpoint_path.is_symlink():
            raise ValueError('Persisted energy checkpoint invalid')
        previous = None
        if checkpoint_path.exists():
            if not checkpoint_path.is_file() or checkpoint_path.stat().st_size > 4096:
                raise ValueError('Persisted energy checkpoint invalid')
            try:
                previous = json.loads(checkpoint_path.read_text())['data']
            except (ValueError, KeyError, TypeError):
                raise ValueError('Persisted energy checkpoint invalid') from None
        check = (guard_type or transport.IndexGuard)(previous)
        check.validate(values, at.timestamp())
        # This is isolated evidence, not a successful native coordinator refresh.
        result['continuityVerified'] = True
    except Exception as error:
        result['reason'] = REASONS.get(str(error), 'read_unverified')
    return result
