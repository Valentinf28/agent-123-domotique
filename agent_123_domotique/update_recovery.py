"""Explicit recovery of a superseded update journal; never installs software."""
from datetime import datetime, timezone
import fcntl
import json
import os
import re
from pathlib import Path
from installation_reset import digest, _valid_uuid


def _save(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY); os.fsync(fd); os.close(fd)
    finally:
        if temporary.exists(): temporary.unlink()


def _eligible(engine, state):
    from installation_update import version, _WORKERS
    engine.require_admin(); engine.require_exclusive()
    if (not state or state.get('state') != 'attention_required'
            or state.get('installSubmitted') is not True
            or not _valid_uuid(state.get('operationId'))
            or str(engine.path) in _WORKERS):
        raise RuntimeError('Le journal ne correspond pas à une ancienne mise à jour terminée sur une autre version.')
    actual = engine.preflight(observe=True)
    current = engine.call('/states/' + actual['entityId']).get('attributes', {})
    if (actual['installedVersion'] != engine.runtime_version
            or version(engine.runtime_version, stable=True) <= version(state.get('targetVersion'), stable=True)
            or current.get('in_progress') is not False or current.get('auto_update') is not False):
        raise RuntimeError('La version et l’absence de mise à jour en cours doivent être vérifiées.')
    return actual


def command(engine, payload, state):
    """Called under the existing update mutex and direct owner-authenticated channel."""
    operation = payload.get('operation')
    allowed = {'operation', 'ownerScope', 'operationId'}
    if operation == 'recovery_commit': allowed |= {'previewHash', 'confirmed', 'backupSlug'}
    if set(payload) - allowed or not _valid_uuid(payload.get('operationId')):
        raise ValueError('Demande de récupération invalide.')
    engine.data.mkdir(exist_ok=True, parents=True)
    fd = os.open(engine.data/'installation-maintenance.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = engine.data/'installation-update-recovery.json'
        if operation == 'recovery_commit' and state.get('state') == 'recovered':
            engine.require_admin()
            prior = json.loads(path.read_text()) if path.exists() else {}
            if (prior.get('phase') != 'completed' or prior.get('operationId') != payload['operationId']
                    or state.get('operationId') != payload['operationId']
                    or prior.get('ownerScope') != payload['ownerScope'] or state.get('ownerScope') != payload['ownerScope']
                    or prior.get('previewHash') != payload.get('previewHash') or payload.get('confirmed') is not True
                    or prior.get('backupSlug') != payload.get('backupSlug')):
                raise RuntimeError('Cette confirmation ne correspond pas à la récupération terminée.')
            return {'state': 'recovered', 'observedVersion': engine.runtime_version,
                    'backupVerified': True, 'oldJournalArchived': True, 'willInstall': False}
        actual = _eligible(engine, state)
        if operation == 'recovery_preview':
            preview = {'operationId': payload['operationId'], 'ownerScope': payload['ownerScope'],
                       'journalDigest': digest(state), 'runtimeVersion': engine.runtime_version,
                       'expiresAt': int(engine.clock())+900, 'phase': 'prepared'}
            preview['previewHash'] = digest(preview)
            _save(path, preview)
            return {'state': 'recovery_prepared', 'operationId': preview['operationId'],
                    'previewHash': preview['previewHash'], 'expiresAt': preview['expiresAt'],
                    'oldTargetVersion': state['targetVersion'], 'observedVersion': engine.runtime_version,
                    'requiresBackup': True, 'willInstall': False}
        if operation != 'recovery_commit': raise ValueError('Opération de récupération inconnue.')
        preview = json.loads(path.read_text()) if path.exists() else {}
        if (payload.get('confirmed') is not True or preview.get('phase') != 'prepared'
                or preview.get('operationId') != payload['operationId']
                or preview.get('ownerScope') != payload['ownerScope']
                or preview.get('previewHash') != payload.get('previewHash')
                or preview.get('expiresAt', 0) < engine.clock()
                or preview.get('runtimeVersion') != engine.runtime_version
                or preview.get('journalDigest') != digest(state)):
            raise RuntimeError('Relisez et confirmez l’aperçu exact de cette récupération.')
        slug = payload.get('backupSlug')
        if not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', slug): raise ValueError('Sauvegarde invalide.')
        info = engine.supervisor('/backups/'+slug+'/info')
        try: date = datetime.fromisoformat(info['date'].replace('Z', '+00:00')).astimezone(timezone.utc).timestamp()
        except Exception as error: raise ValueError('Date de sauvegarde invalide.') from error
        addons = info.get('addons', info.get('apps', []))
        if (info.get('slug') != slug or info.get('type') != 'full' or not info.get('homeassistant')
                or info.get('homeassistant_exclude_database') is not False
                or not -30 <= engine.clock()-date <= 3600
                or not any(a.get('slug') == actual['slug'] for a in addons)):
            raise RuntimeError('Une sauvegarde complète récente incluant cet agent est nécessaire.')
        proof = engine.verify_archive(slug)
        if not isinstance(proof, dict) or proof.get('verified') is not True or actual['slug'] not in proof.get('addons', []):
            raise RuntimeError('Le contenu réel de la sauvegarde n’a pas été vérifié.')
        latest = engine.load()
        if digest(latest) != preview['journalDigest']: raise RuntimeError('Le journal a changé pendant la vérification.')
        _eligible(engine, latest)
        archive = engine.data/('installation-update-retired-'+preview['operationId']+'.json')
        record = {'original': latest, 'recovery': {**preview, 'phase': 'archived', 'backupSlug': slug, 'backupProof': proof}}
        if archive.exists():
            if archive.is_symlink() or json.loads(archive.read_text()) != record:
                raise RuntimeError('Une archive différente existe ; vérification opérateur nécessaire.')
        else:
            afd = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(afd, 'w') as stream:
                json.dump(record, stream); stream.flush(); os.fsync(stream.fileno())
        dirfd = os.open(engine.data, os.O_RDONLY); os.fsync(dirfd); os.close(dirfd)
        # Preserve an explicit recovery marker; never claim the old install succeeded.
        engine.save({'operationId': preview['operationId'], 'ownerScope': preview['ownerScope'],
                     'state': 'recovered', 'observedVersion': engine.runtime_version,
                     'installSubmitted': False, 'recoveryArchive': archive.name})
        preview['phase'] = 'completed'; preview['backupSlug'] = slug; _save(path, preview)
        return {'state': 'recovered', 'observedVersion': engine.runtime_version,
                'backupVerified': True, 'oldJournalArchived': True, 'willInstall': False}
