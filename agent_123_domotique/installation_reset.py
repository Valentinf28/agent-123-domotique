"""Portal initiated installation reset. No raw HA storage, account or network writes.

All destructive steps require a durable, owner-bound preview and a completed full
backup whose archive was actually read. Restarted workers never resume deletion.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
import urllib.parse

TTL = 15 * 60
# Only equipment integrations explicitly supported by the product are reset.
# Infrastructure, backup destinations and unknown integrations are preserved.
EQUIPMENT_DOMAINS = frozenset('labox_ddzy422 solarman deye shelly tuya overkiz somfy midea_ac midea lan_midea lektrico ocpp easee wallbox goecharger go_e_charger open_evse openevse zaptec tesla tesla_custom tesla_fleet nuki mqtt esphome zha zwave_js hue matter homekit_controller homekit_device switchbot tado netatmo daikin melcloud panasonic_cc lg_thinq smartthings broadlink modbus goodwe growatt_server huawei_solar fronius sma solaredge enphase_envoy hoymiles open_dtu apsystems aioshelly ms_pa mspa'.split())
# mqtt and radio coordinators can carry many devices; the exact entry is listed
# in the preview, while their add-ons and network stay untouched.
_WORKERS = {}
_MUTEX = threading.RLock()
SAFE_ERRORS = {
    'backup': 'La sauvegarde complète n’a pas pu être vérifiée. Aucun appareil n’a été supprimé.',
    'changed': 'La configuration a changé. Préparez une nouvelle vérification avant de poursuivre.',
    'partial': 'La remise à zéro est interrompue. Vérifiez les éléments restants avant de la reprendre.',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _valid_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


class Reset:
    def __init__(self, call, supervisor, verify_archive, *, authorize=None, data=Path('/data'), clock=time.time, sleep=time.sleep, backup_guard=None):
        self.call, self.supervisor, self.verify_archive = call, supervisor, verify_archive
        self.authorize = authorize
        self.backup_guard = backup_guard
        self.data, self.clock, self.sleep = Path(data), clock, sleep
        self.path = self.data / 'installation-reset.json'

    def require_admin(self):
        try:
            current = self.authorize() if self.authorize else None
        except Exception:
            current = None
        if not isinstance(current, dict) or current.get('is_admin') is not True:
            raise RuntimeError('Cette box ne dispose pas des droits Home Assistant nécessaires à la remise à zéro. Aucun contournement des permissions n’est effectué.')

    def load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, state):
        self.data.mkdir(exist_ok=True, parents=True)
        temp = self.path.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(state, file); file.flush(); os.fsync(file.fileno())
        os.replace(temp, self.path)
        fd = os.open(self.data, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def snapshot(self):
        entries = self.call('/config/config_entries/entry')
        states = self.call('/states')
        if not isinstance(entries, list) or not isinstance(states, list):
            raise RuntimeError('La configuration de cette box est indisponible.')
        selected, retained, fingerprints, automations, reasons = [], [], {}, [], []
        for entry in entries:
            eid, domain = entry.get('entry_id'), entry.get('domain')
            if not isinstance(eid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', eid) or not isinstance(domain, str):
                raise RuntimeError('Inventaire des intégrations incomplet.')
            view = {'entryId': eid, 'domain': domain, 'title': str(entry.get('title', domain))[:200]}
            if domain in EQUIPMENT_DOMAINS and entry.get('source') not in ('ignore', 'system', 'hassio'):
                selected.append(view)
                if entry.get('supports_unload') is False:
                    reasons.append('Une intégration nécessite un redémarrage et doit être vérifiée : ' + view['title'])
                # Stable configuration fields, excluding load-state/retry churn.
                fingerprints[eid] = digest({k: v for k, v in entry.items() if k not in ('state', 'reason', 'num_subentries', 'supports_unload', 'supports_reconfigure', 'supports_options', 'supports_remove_device')})
            else:
                retained.append(view)
        for entity in states:
            entity_id = entity.get('entity_id', '')
            if not entity_id.startswith('automation.'):
                continue
            attrs = entity.get('attributes', {})
            identifier = attrs.get('id')
            view = {'entityId': entity_id, 'name': str(attrs.get('friendly_name', entity_id))[:200], 'id': identifier if isinstance(identifier, str) else ''}
            automations.append(view)
            if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', identifier):
                reasons.append('Un automatisme sans identifiant ne peut pas être supprimé à distance : ' + view['name'])
                continue
            try:
                config = self.call('/config/automation/config/' + identifier)
                if not isinstance(config, dict) or str(config.get('id', '')) != identifier:
                    raise ValueError('not editable')
                fingerprints['automation:' + identifier] = digest(config)
            except Exception:
                reasons.append('Un automatisme YAML ou non modifiable doit être vérifié : ' + view['name'])
        if len({a['id'] for a in automations}) != len(automations):
            reasons.append('Des identifiants d’automatismes sont ambigus.')
        return {'entries': sorted(selected, key=lambda x: x['entryId']),
                'automations': sorted(automations, key=lambda x: x['entityId']),
                'preservedEntries': sorted(retained, key=lambda x: x['entryId']),
                'fingerprints': fingerprints, 'blockedReasons': reasons}

    def public(self, state):
        if not state: return {'state': 'idle'}
        keys = ('operationId', 'previewHash', 'expiresAt', 'state', 'entries', 'automations', 'preservedEntries', 'blockedReasons', 'backupVerified', 'backupSlug', 'removedEntryIds', 'removedAutomationIds', 'error')
        return {k: state[k] for k in keys if k in state}

    def reconcile(self, state):
        self.require_admin()
        current = self.snapshot()
        removed = set(state.get('removedEntryIds', []))
        removed_a = set(state.get('removedAutomationIds', []))
        # A response lost after DELETE is reconciled from the actual inventory,
        # but missing anything other than the single journaled intent is refused.
        intent = state.get('intent')
        if intent:
            key, identifier = intent['kind'], intent['id']
            if key == 'entry' and identifier not in {e['entryId'] for e in current['entries']}:
                removed.add(identifier)
            if key == 'automation' and identifier not in {a['id'] for a in current['automations']}:
                removed_a.add(identifier)
        expected = {k: v for k, v in state['fingerprints'].items()
                    if k not in removed and not (k.startswith('automation:') and k[11:] in removed_a)}
        if (current['fingerprints'] != expected or current['blockedReasons']
                or current['preservedEntries'] != state['preservedEntries']):
            raise RuntimeError(SAFE_ERRORS['changed'])
        state.update(removedEntryIds=sorted(removed), removedAutomationIds=sorted(removed_a))
        state.pop('intent', None)
        return state

    def backup(self, state):
        self.require_admin()
        # Unique name allows reconciliation after a lost POST response. Never
        # submit another backup for the same operation after an uncertain send.
        name = getattr(self, 'backup_name', 'La Box avant reconfiguration ') + state['operationId']
        if not state.get('backupSubmitted'):
            state['backupSubmitted'] = True
            self.save(state)
            result = self.supervisor('/backups/new/full', method='POST', payload={
                'name': name, 'background': True, 'homeassistant_exclude_database': False,
                'location': None}, timeout=30)
            if result.get('slug'): state['backupSlug'] = result['slug']
            if result.get('job_id'): state['backupJobId'] = result['job_id']
            self.save(state)
        for _ in range(360):
            listing = self.supervisor('/backups')
            candidates = [b for b in listing.get('backups', []) if b.get('name') == name]
            if len(candidates) > 1: raise RuntimeError(SAFE_ERRORS['backup'])
            if candidates:
                slug = candidates[0].get('slug', '')
                if not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', slug):
                    raise RuntimeError(SAFE_ERRORS['backup'])
                info = self.supervisor('/backups/' + slug + '/info')
                if (info.get('slug') != slug or info.get('name') != name or info.get('type') != 'full'
                        or not info.get('homeassistant') or info.get('homeassistant_exclude_database') is not False
                        or not isinstance(info.get('size'), (int, float)) or info['size'] <= 0):
                    raise RuntimeError(SAFE_ERRORS['backup'])
                own = self.supervisor('/addons/self/info').get('slug')
                addons = info.get('addons', info.get('apps', []))
                if not own or not any(a.get('slug') == own for a in addons):
                    raise RuntimeError(SAFE_ERRORS['backup'])
                # Actual archive read and tar validation, not creation acknowledgement.
                proof = self.verify_archive(slug)
                if (not isinstance(proof, dict) or proof.get('verified') is not True or own not in proof.get('addons', [])):
                    raise RuntimeError(SAFE_ERRORS['backup'])
                state.update(backupSlug=slug, backupVerified=True, backupArchive=proof)
                self.save(state)
                return
            self.sleep(5)
        raise RuntimeError(SAFE_ERRORS['backup'])

    def work(self, operation_id):
        try:
            # Process-wide and OS locks prevent a second worker/add-on instance.
            self.data.mkdir(exist_ok=True, parents=True)
            fd = os.open(self.data / 'installation-maintenance.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                state = self.load()
                if state.get('operationId') != operation_id: return
                if self.backup_guard:self.backup_guard()
                self.backup(state)
                state = self.reconcile(state)
                state['state'] = 'removing'; self.save(state)
                # Remove editable automations before integrations so no stale
                # automation can command an equipment during reconfiguration.
                for item in state['automations']:
                    if item['id'] in state['removedAutomationIds']: continue
                    state = self.reconcile(state)
                    state['intent'] = {'kind': 'automation', 'id': item['id']}; self.save(state)
                    self.call('/services/automation/turn_off', method='POST', payload={'entity_id': item['entityId'], 'stop_actions': True})
                    self.call('/config/automation/config/' + item['id'], method='DELETE')
                    # Reload is needed on HA versions where config DELETE only
                    # removes registry/config and leaves the runtime automation.
                    self.call('/services/automation/reload', method='POST', payload={})
                    state = self.reconcile(state); self.save(state)
                    if item['id'] not in state['removedAutomationIds']: raise RuntimeError(SAFE_ERRORS['partial'])
                for item in state['entries']:
                    if item['entryId'] in state['removedEntryIds']: continue
                    state = self.reconcile(state)
                    state['intent'] = {'kind': 'entry', 'id': item['entryId']}; self.save(state)
                    response = self.call('/config/config_entries/entry/' + item['entryId'], method='DELETE')
                    if not isinstance(response, dict) or response.get('require_restart') is True:
                        # Never remotely restart HA and risk losing control.
                        state['blockedReasons'].append('Home Assistant demande un redémarrage avant de poursuivre. Les équipements restants sont conservés.')
                        self.save(state)
                        raise RuntimeError(SAFE_ERRORS['partial'])
                    state = self.reconcile(state); self.save(state)
                    if item['entryId'] not in state['removedEntryIds']: raise RuntimeError(SAFE_ERRORS['partial'])
                state['state'] = 'completed'; state.pop('error', None); self.save(state)
        except Exception:
            with _MUTEX:
                state = self.load()
                if state.get('operationId') != operation_id: return
                state['state'] = 'partial' if state.get('backupVerified') else 'backup_uncertain'
                state['error'] = SAFE_ERRORS['partial' if state.get('backupVerified') else 'backup']
                self.save(state)
        finally:
            with _MUTEX: _WORKERS.pop(str(self.path), None)

    def command(self, payload):
        owner = payload.get('ownerScope')
        if not isinstance(owner, str) or not re.fullmatch('[a-f0-9]{64}', owner):
            raise RuntimeError('Le propriétaire de cette maison doit être vérifié.')
        operation = payload.get('operation')
        if operation in ('prepare', 'execute'):
            from installation_update import busy
            if self.backup_guard:self.backup_guard()
            if busy(self.data):raise RuntimeError('Terminez la mise à jour avant de recommencer l’installation.')
            self.require_admin()
        with _MUTEX:
            state = self.load()
            if state and state.get('ownerScope') != owner:
                if (operation == 'prepare' and _valid_uuid(payload.get('operationId'))
                        and (state.get('state') in ('completed', 'failed')
                             or (state.get('state') == 'prepared' and not state.get('backupSubmitted')))
                        and not _WORKERS.get(str(self.path))):
                    # A later legitimate owner may start fresh, but never sees
                    # the former owner's names, backup proof or operation data.
                    archive = self.data / ('installation-reset-' + state['operationId'] + '.json')
                    fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'w') as file:
                        json.dump(state, file); file.flush(); os.fsync(file.fileno())
                    state = {}
                else:
                    raise RuntimeError('Cette préparation appartient à un autre accès propriétaire.')
            active = _WORKERS.get(str(self.path))
            if state.get('state') in ('backing_up', 'removing') and not active:
                state['state'] = 'partial' if state.get('backupVerified') else 'backup_uncertain'
                state['error'] = SAFE_ERRORS['partial' if state.get('backupVerified') else 'backup']
                self.save(state)
            if operation == 'status': return self.public(state)
            identifier = payload.get('operationId')
            if not _valid_uuid(identifier): raise RuntimeError('Identifiant de remise à zéro invalide.')
            if operation == 'prepare':
                if state.get('operationId') == identifier:
                    if (state.get('state') in ('partial', 'backup_uncertain') or (state.get('state') == 'prepared' and self.clock() > state['expiresAt'])) and not active:
                        state = self.reconcile(state)
                        state['expiresAt'] = int(self.clock()) + TTL
                        state['previewHash'] = digest({k: state[k] for k in ('operationId', 'ownerScope', 'expiresAt', 'entries', 'automations', 'preservedEntries', 'fingerprints', 'removedEntryIds', 'removedAutomationIds')})
                        self.save(state)
                    return self.public(state)
                if active or state.get('state') in ('partial', 'backup_uncertain'):
                    raise RuntimeError('La remise à zéro précédente doit d’abord être vérifiée.')
                snapshot = self.snapshot()
                state = {**snapshot, 'operationId': identifier, 'ownerScope': owner,
                         'expiresAt': int(self.clock()) + TTL, 'state': 'prepared',
                         'backupVerified': False, 'removedEntryIds': [], 'removedAutomationIds': []}
                state['previewHash'] = digest({k: state[k] for k in ('operationId', 'ownerScope', 'expiresAt', 'entries', 'automations', 'preservedEntries', 'fingerprints')})
                self.save(state); return self.public(state)
            if operation != 'execute' or identifier != state.get('operationId'):
                raise RuntimeError('Préparation de remise à zéro introuvable.')
            if payload.get('previewHash') != state.get('previewHash') or payload.get('confirmation') != 'RECOMMENCER':
                raise RuntimeError('Confirmez exactement la préparation affichée.')
            if state.get('state') == 'completed' or active: return self.public(state)
            if state.get('blockedReasons'): raise RuntimeError('Des automatismes non modifiables empêchent la remise à zéro.')
            # A partial run can only resume within the original confirmation TTL.
            if self.clock() > state['expiresAt']: raise RuntimeError('Cette confirmation a expiré. Une vérification est nécessaire.')
            state = self.reconcile(state)
            state['state'] = 'backing_up'; state.pop('error', None); self.save(state)
            worker = threading.Thread(target=self.work, args=(identifier,), daemon=True, name='installation-reset')
            _WORKERS[str(self.path)] = worker
            worker.start()
            return self.public(state)


def blocks_mutations(data=Path('/data')):
    """Fail closed for corrupt journals, permit read-only diagnostics."""
    factory = Path(data) / 'factory-stage.json'
    if factory.exists():
        try:
            staged=json.loads(factory.read_text())
            if staged.get('state') in ('preparing','prepared','committing'): return True
            if staged.get('state')=='committed':
                identity=Path(data)/'agent-state.json'
                if not identity.exists():return True
                current=json.loads(identity.read_text())
                from factory_stage import retired_identity
                if not current.get('token') or retired_identity(current,data):return True
        except Exception: return True
    path = Path(data) / 'installation-reset.json'
    from installation_update import busy
    if busy(data):return True
    if not path.exists(): return False
    try:
        return json.loads(path.read_text()).get('state') in ('backing_up', 'removing', 'partial', 'backup_uncertain')
    except Exception:
        return True


def verify_supervisor_archive(slug, token):
    """Read the real local archive completely; validate tar headers and payloads."""
    import tarfile
    import gzip
    import urllib.request
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', slug):
        raise RuntimeError(SAFE_ERRORS['backup'])
    request = urllib.request.Request('http://supervisor/backups/' + slug + '/download', headers={'Authorization': 'Bearer ' + token})
    checksum = hashlib.sha256(); total = 0; metadata = None; homeassistant = False; members = set()
    with urllib.request.urlopen(request, timeout=60) as response:
        class Reader:
            def read(self, size=-1):
                nonlocal total
                block = response.read(size); checksum.update(block); total += len(block); return block
        reader = Reader()
        with tarfile.open(fileobj=reader, mode='r|*') as archive:
            for member in archive:
                name = member.name[2:] if member.name.startswith('./') else member.name
                if member.isfile():
                    members.add(name)
                    content = archive.extractfile(member)
                    if name == 'backup.json':
                        if member.size > 1024 * 1024: raise RuntimeError(SAFE_ERRORS['backup'])
                        metadata = json.loads(content.read())
                    elif name.endswith(('.tar.gz', '.tar')):
                        # Validate inner archives too, including gzip CRC/footer.
                        inner = gzip.GzipFile(fileobj=content) if name.endswith('.gz') else content
                        with tarfile.open(fileobj=inner, mode='r|') as nested:
                            for nested_member in nested:
                                if nested_member.isfile():
                                    nested_content = nested.extractfile(nested_member)
                                    while nested_content.read(1024 * 1024): pass
                        while inner.read(1024 * 1024): pass
                        if inner is not content: inner.close()
                    else:
                        while content.read(1024 * 1024): pass
                    if name in ('homeassistant.tar.gz', 'homeassistant.tar') and member.size > 0:
                        homeassistant = True
        # Consume trailing blocks so interrupted downloads fail before deletion.
        while reader.read(1024 * 1024): pass
    if (not isinstance(metadata, dict) or metadata.get('slug') != slug or metadata.get('type') != 'full'
            or not isinstance(metadata.get('homeassistant'), dict)
            or metadata['homeassistant'].get('exclude_database') is not False
            or not homeassistant or total <= 1024):
        raise RuntimeError(SAFE_ERRORS['backup'])
    addons = [a.get('slug') for a in metadata.get('addons', metadata.get('apps', []))
              if isinstance(a, dict) and isinstance(a.get('slug'), str)
              and any(a['slug'] + suffix in members for suffix in ('.tar.gz', '.tar'))]
    return {'verified': True, 'sha256': checksum.hexdigest(), 'bytes': total, 'addons': addons}
