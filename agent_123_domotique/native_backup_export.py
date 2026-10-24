"""Resumable native HAOS exports. No restore, retention change, shell or arbitrary URL.
Adapters must enforce native device auth and the fixed portal destination.
"""
import asyncio
import fcntl
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile
import time
import uuid
from datetime import datetime
from recovery_securearchive import verify_archive, ArchiveRejected

MAX_BYTES = 5 * 1024 ** 3
CHUNK_BYTES = 4 * 1024 ** 2
SLUG = re.compile(r'[A-Za-z0-9_-]{1,80}')
HEX = re.compile(r'[a-f0-9]{64}')

def is_slug(value):
    return isinstance(value, str) and value not in {'config', 'info', 'new'} and bool(SLUG.fullmatch(value))

class ExportRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def timestamp(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value) or value <= 0: raise ValueError()
            return value / 1000
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError):
        raise ExportRejected('INVALID_EXPIRY') from None

def read_private(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid() or info.st_size > 65536:
            raise ExportRejected('PRIVATE_FILE_UNSAFE')
        return json.loads(f.read())

def write_private(path, value):
    if path.is_symlink():
        raise ExportRejected('PRIVATE_FILE_UNSAFE')
    fd, temp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(value, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def read_key_input(data):
    if not isinstance(data, bytes) or len(data) > 16384:
        raise ExportRejected('INVALID_RECOVERY_KIT')
    try:
        text = data.decode('utf8').replace('\r\n', '\n').strip()
    except UnicodeError:
        raise ExportRejected('INVALID_RECOVERY_KIT') from None
    match = re.search(r'^(?:Encryption key|Clé de chiffrement|Native backup password):\s*(.+)$', text, re.M | re.I)
    native_keys = re.findall(r'(?m)^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){6}$', text)
    if len(native_keys) > 1:
        raise ExportRejected('INVALID_RECOVERY_KIT')
    password = match.group(1).strip() if match else (native_keys[0] if native_keys else text)
    if '\n' in password or not 1 <= len(password) <= 4096:
        raise ExportRejected('INVALID_RECOVERY_KIT')
    return password

class NativeBackupExportWorker:
    """supervisor: json(method,path,body=None), download(slug) async iterator.
    portal: status(job), post(job,body), put(job,offset,bytes,sha256),
            recovery_input(job), recovery_kit(job,nonce,bytes).
    No adapter is allowed to expose upstream credentials or native error text.
    """
    def __init__(self, root, supervisor, portal, *, clock=time.time, verifier=verify_archive, maintenance_lock=None, maintenance_busy=None):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ExportRejected('PRIVATE_DIRECTORY_UNSAFE')
        self.supervisor, self.portal, self.clock, self.verifier = supervisor, portal, clock, verifier
        self.maintenance_lock = Path(maintenance_lock) if maintenance_lock is not None else self.root / "maintenance.lock"
        self.maintenance_busy = maintenance_busy

    def validate_job(self, job):
        if not isinstance(job, dict) or job.get('protocol') != 1:
            raise ExportRejected('INVALID_JOB')
        try:
            if str(uuid.UUID(job['exportId'])) != job['exportId']:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ExportRejected('INVALID_JOB') from None
        if not re.fullmatch(r'[a-f0-9]{32}', str(job.get('nonce'))) or not HEX.fullmatch(str(job.get('bindingGeneration'))):
            raise ExportRejected('INVALID_JOB')
        if job.get('ownerScope') is not None and not HEX.fullmatch(str(job['ownerScope'])):
            raise ExportRejected('INVALID_JOB')
        if job.get('mode') not in ('create_full', 'existing') or job.get('maxBytes') != MAX_BYTES or job.get('chunkBytes') != CHUNK_BYTES:
            raise ExportRejected('INVALID_JOB')
        if job['mode'] == 'existing' and not is_slug(job.get('backupId')):
            raise ExportRejected('INVALID_JOB')
        if job['mode'] == 'create_full' and job.get('backupId') is not None and not is_slug(job['backupId']):
            raise ExportRejected('INVALID_JOB')
        timestamp(job.get('expiresAt'))

    async def checked_status(self, job):
        self.validate_job(job)
        status = await self.portal.status(job)
        if not isinstance(status, dict) or status.get('bindingGeneration') != job['bindingGeneration']:
            raise ExportRejected('BINDING_CHANGED')
        if status.get('state') in ('cancelled', 'failed', 'expired'):
            raise ExportRejected('CANCELLED')
        if timestamp(job['expiresAt']) <= self.clock() and status.get('state') not in ('ready', 'completed'):
            raise ExportRejected('EXPIRED')
        if timestamp(status.get('expiresAt')) <= self.clock():
            raise ExportRejected('EXPIRED')
        offset = status.get('offset')
        if type(offset) is not int or not 0 <= offset <= MAX_BYTES:
            raise ExportRejected('INVALID_OFFSET')
        return status

    def save(self, job, state):
        write_private(self.root / (job['exportId'] + '.json'), state)

    async def preflight(self, job):
        await self.checked_status(job)
        mine = await self.supervisor.json('GET', '/addons/self/info')
        addons = await self.supervisor.json('GET', '/addons')
        own = mine.get('slug')
        expected = sorted({x.get('slug') for x in addons.get('addons', []) if isinstance(x, dict) and is_slug(x.get('slug'))})
        if not is_slug(own) or own not in expected:
            raise ExportRejected('NATIVE_INVENTORY_INCOMPLETE')
        if job['mode'] == 'create_full':
            await self.check_create_quota(job)
        return own, expected, ['addons/local', 'media', 'share', 'ssl']

    async def check_create_quota(self, job):
        current = await self.checked_status(job)
        limit = current.get('maxLocalBackups')
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ExportRejected('NATIVE_POLICY_INVALID')
        inventory = await self.supervisor.json('GET', '/backups')
        backups = inventory.get('backups')
        if not isinstance(backups, list): raise ExportRejected('NATIVE_INVENTORY_INCOMPLETE')
        if len(backups) >= limit: raise ExportRejected('NATIVE_BACKUP_LIMIT')

    async def archive_id(self, job, state):
        if state.get('backupId'):
            return state['backupId']
        listing = await self.supervisor.json('GET', '/backups')
        matches = [x for x in listing.get('backups', []) if x.get('name') == state['marker']]
        if len(matches) > 1:
            raise ExportRejected('AMBIGUOUS_NATIVE_BACKUP')
        if matches and is_slug(matches[0].get('slug')):
            state['backupId'] = matches[0]['slug']; state['phase'] = 'created'; self.save(job, state)
            return state['backupId']
        return None  # An uncertain create is never repeated, even after restart.

    @contextmanager
    def locked(self):
        handles = []
        try:
            for path in (self.maintenance_lock, self.root / 'worker.lock'):
                fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                handle = os.fdopen(fd, 'r+')
                handles.append(handle)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ExportRejected('PRIVATE_FILE_UNSAFE')
                try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    yield False
                    return
            yield True
        finally:
            for handle in reversed(handles): handle.close()

    async def reconcile_active(self, except_export_id=None):
        """Read-only server reconciliation for jobs no longer delivered in polls."""
        if self.maintenance_busy is None:
            return  # No native idle proof: never unlock maintenance by guessing.
        with self.locked() as acquired:
            if not acquired or await self.maintenance_busy(): return
            for path in self.root.glob('*.json'):
                if path.name.endswith('.key.json'): continue
                state = read_private(path)
                if not state or state.get('phase') not in ('planned','creating','created','uploading'): continue
                old = state.get('job', {})
                if old.get('exportId') == except_export_id: continue
                try:
                    await self.checked_status(old)
                except ExportRejected as error:
                    if error.code in ('CANCELLED','EXPIRED','BINDING_CHANGED','NATIVE_AUTH_CHANGED'):
                        state.update(phase='cancelled_safe',localExpiresAt=self.clock()+24*3600)
                        self.save(old,state)
                # A transport failure or still-active response preserves the lock.

    async def tick(self, job):
        try:
            return await self._tick(job)
        except ExportRejected as error:
            public = {
                'NATIVE_BACKUP_LIMIT':'native_limit',
                'INSUFFICIENT_LOCAL_SPACE':'capacity',
                'NATIVE_ARCHIVE_UNVERIFIED':'integrity',
                'NATIVE_HASH_CHANGED':'integrity',
                'NATIVE_STREAM_TRUNCATED':'integrity',
                'NATIVE_SIZE_INVALID':'capacity',
                'NATIVE_INVENTORY_CHANGED':'integrity',
                'NATIVE_BACKUP_NOT_ENCRYPTED_FULL':'not_full',
            }.get(error.code)
            if public:
                try:
                    # Re-authenticate the exact job; never report through a stale
                    # owner binding, and never terminalize a network uncertainty.
                    await self.checked_status(job)
                    await self.portal.post(job, {'phase':'failed','code':public})
                except Exception:
                    pass
            raise

    async def _tick(self, job):
        self.validate_job(job)
        await self.reconcile_active(job['exportId'])
        with self.locked() as acquired:
            if not acquired:
                return {'state': 'busy'}
            if self.maintenance_busy is not None and await self.maintenance_busy():
                return {'state': 'busy'}
            path = self.root / (job['exportId'] + '.json')
            state = read_private(path)
            if state and any(state.get('job', {}).get(k) != job.get(k) for k in ('exportId','nonce','bindingGeneration','ownerScope','mode','maxBytes','chunkBytes')):
                raise ExportRejected('JOB_CHANGED')
            try:
                status = await self.checked_status(job)
            except ExportRejected as error:
                if state and self.maintenance_busy is not None and error.code in ('CANCELLED','EXPIRED','BINDING_CHANGED','NATIVE_AUTH_CHANGED'):
                    # Callback just proved no native backup/maintenance operation is active.
                    # Never delete the native archive; only retire this transfer journal.
                    state.update(phase='cancelled_safe', localExpiresAt=self.clock()+24*3600)
                    self.save(job,state)
                raise
            if state is None and self.busy():
                return {'state': 'busy'}
            if state is not None and state.get('phase') == 'ready':
                await self.deliver_recovery(job, state)
                return {'state': 'ready', 'bytes': state['bytes'], 'backupId': state['backupId']}
            if state is None:
                own, addons, folders = await self.preflight(job)
                state = {'schema': 1, 'job': job, 'phase': 'planned', 'marker': 'La Box export ' + job['exportId'],
                         'sourceAddon': own, 'expectedAddons': addons, 'expectedFolders': folders,
                         'backupId': job.get('backupId') if job['mode']=='existing' else None, 'verified': False}
                self.save(job, state)
            keypath = self.root / (job['exportId'] + '.key.json')
            if job['mode'] == 'create_full' and state['phase'] == 'planned':
                key = read_private(keypath)
                if key is None:
                    key = {'password': secrets.token_urlsafe(48), 'bindingGeneration': job['bindingGeneration']}
                    write_private(keypath, key)
                if key.get('bindingGeneration') != job['bindingGeneration'] or not isinstance(key.get('password'), str) or not 32 <= len(key['password']) <= 4096:
                    raise ExportRejected('KEY_BINDING_CHANGED')
                await self.check_create_quota(job)
                await self.portal.post(job, {'phase': 'creating'})
                state['phase'] = 'creating'; self.save(job, state)
                # Native encryption only. Background operation may stop this add-on.
                result = await self.supervisor.json('POST', '/backups/new/full', {
                    'name': state['marker'], 'password': key['password'], 'location': None,
                    'compressed': True, 'homeassistant_exclude_database': False, 'background': True})
                if isinstance(result, dict):
                    state['nativeJobId'] = result.get('job_id')
                    if isinstance(result.get('slug'), str) and SLUG.fullmatch(result['slug']):
                        state['backupId'] = result['slug']
                    self.save(job, state)
            backup_id = await self.archive_id(job, state)
            if backup_id is None:
                return {'state': 'creating'}
            await self.checked_status(job)
            metadata = await self.supervisor.json('GET', '/backups/' + backup_id + '/info')
            local_folders = set(metadata.get('folders', [])) & {'addons/local', 'apps/local'}
            if len(local_folders) != 1:
                raise ExportRejected('NATIVE_INVENTORY_INCOMPLETE')
            expected_folders = sorted(['media', 'share', 'ssl', *local_folders])
            if state.get('downloaded') and state['expectedFolders'] != expected_folders:
                raise ExportRejected('NATIVE_INVENTORY_CHANGED')
            state['expectedFolders'] = expected_folders
            if metadata.get('type') != 'full' or metadata.get('protected') is not True:
                raise ExportRejected('NATIVE_BACKUP_NOT_ENCRYPTED_FULL')
            spool = self.root / (job['exportId'] + '.tar')
            if not state.get('downloaded'):
                expected_size = metadata.get('size_bytes')
                if type(expected_size) is not int or not 0 < expected_size <= MAX_BYTES:
                    raise ExportRejected('NATIVE_SIZE_INVALID')
                if shutil.disk_usage(self.root).free < expected_size + 256 * 1024 ** 2:
                    raise ExportRejected('INSUFFICIENT_LOCAL_SPACE')
                if spool.exists() or spool.is_symlink():
                    info = spool.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                        raise ExportRejected('PRIVATE_FILE_UNSAFE')
                    spool.unlink()
                fd = os.open(spool, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                count, digest = 0, hashlib.sha256()
                with os.fdopen(fd, 'wb') as out:
                    async for chunk in self.supervisor.download(backup_id):
                        await self.checked_status(job)
                        if not isinstance(chunk, bytes) or len(chunk) > CHUNK_BYTES:
                            raise ExportRejected('NATIVE_STREAM_INVALID')
                        count += len(chunk)
                        if count > expected_size or count > MAX_BYTES:
                            raise ExportRejected('NATIVE_SIZE_INVALID')
                        out.write(chunk); digest.update(chunk)
                    out.flush(); os.fsync(out.fileno())
                if count != expected_size:
                    raise ExportRejected('NATIVE_STREAM_TRUNCATED')
                state.update(downloaded=True, bytes=count, sha256=digest.hexdigest()); self.save(job, state)
            key = read_private(keypath)
            if not key and job['mode'] == 'existing':
                for candidate in self.root.glob('*.json'):
                    if candidate.name.endswith('.key.json'): continue
                    previous = read_private(candidate)
                    if previous and previous.get('backupId') == backup_id and previous.get('job', {}).get('bindingGeneration') == job['bindingGeneration']:
                        key = read_private(self.root / (previous['job']['exportId'] + '.key.json'))
                        if key: break
            if key and (key.get('bindingGeneration') != job['bindingGeneration'] or not isinstance(key.get('password'), str) or not 1 <= len(key['password']) <= 4096):
                raise ExportRejected('KEY_BINDING_CHANGED')
            if not key:
                await self.portal.post(job, {'phase': 'key_required'})
                supplied = await self.portal.recovery_input(job)
                if not supplied:
                    return {'state': 'awaiting_key'}
                key = {'password': read_key_input(supplied), 'bindingGeneration': job['bindingGeneration'], 'imported': True}
            current_self = await self.supervisor.json('GET', '/addons/self/info')
            current_apps = await self.supervisor.json('GET', '/addons')
            current_slugs = sorted({x.get('slug') for x in current_apps.get('addons', []) if isinstance(x, dict) and is_slug(x.get('slug'))})
            if current_self.get('slug') != state['sourceAddon'] or current_slugs != state['expectedAddons']:
                raise ExportRejected('NATIVE_INVENTORY_CHANGED')
            # Do not trust a stale verification flag: read all encrypted bytes again after restart.
            fd = os.open(spool, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid() or info.st_size != state['bytes']:
                    raise ExportRejected('PRIVATE_FILE_UNSAFE')
                try:
                    proof = self.verifier(stream, key['password'], backup_id, state['sourceAddon'],
                                          expected_addons=state['expectedAddons'], expected_folders=state['expectedFolders'])
                except ArchiveRejected:
                    if job['mode'] == 'create_full':
                        raise ExportRejected('NATIVE_ARCHIVE_UNVERIFIED') from None
                    await self.portal.post(job, {'phase': 'key_required', 'code': 'key_invalid'})
                    return {'state': 'awaiting_key'}
            if proof.get('sha256') != state['sha256'] or proof.get('bytes') != state['bytes']:
                raise ExportRejected('NATIVE_HASH_CHANGED')
            proof['sourceAddon'] = state['sourceAddon']
            proof['keyState'] = 'external' if key.get('imported') else 'available'
            state.update(verified=True, proof=proof, phase='uploading'); self.save(job, state)
            if not read_private(keypath):
                write_private(keypath, key)
            await self.checked_status(job)
            await self.portal.post(job, {'phase': 'manifest', 'backupId': backup_id, 'bytes': state['bytes']})
            status = await self.checked_status(job); offset = status['offset']
            if offset > state['bytes'] or offset % CHUNK_BYTES and offset != state['bytes']:
                raise ExportRejected('INVALID_OFFSET')
            fd = os.open(spool, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                stream.seek(offset)
                while offset < state['bytes']:
                    await self.checked_status(job)
                    chunk = stream.read(min(CHUNK_BYTES, state['bytes'] - offset))
                    if not chunk:
                        raise ExportRejected('NATIVE_STREAM_TRUNCATED')
                    reply = await self.portal.put(job, offset, chunk, hashlib.sha256(chunk).hexdigest())
                    offset += len(chunk)
                    if reply.get('offset') != offset:
                        raise ExportRejected('INVALID_OFFSET')
            await self.checked_status(job)
            await self.portal.post(job, {'phase': 'complete', 'sha256': state['sha256'], 'proof': proof})
            state['phase'] = 'ready'; state['localExpiresAt'] = self.clock() + 24 * 3600; self.save(job, state)
            await self.deliver_recovery(job, state, key)
            return {'state': 'ready', 'bytes': state['bytes'], 'backupId': backup_id}

    async def deliver_recovery(self, job, state=None, key=None):
        status = await self.checked_status(job)
        request = status.get('recoveryRequest')
        if not request:
            return False
        if not isinstance(request, dict) or not re.fullmatch(r'(?:[a-f0-9]{32,64}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})', str(request.get('nonce'))) or timestamp(request.get('expiresAt')) <= self.clock():
            raise ExportRejected('INVALID_RECOVERY_REQUEST')
        state = state or read_private(self.root / (job['exportId'] + '.json'))
        key = key or read_private(self.root / (job['exportId'] + '.key.json'))
        if not state or not state.get('verified') or not key or key.get('bindingGeneration') != job['bindingGeneration']:
            raise ExportRejected('RECOVERY_KEY_UNAVAILABLE')
        kit = ('La Box — Native Home Assistant backup recovery\nBackup: ' + state['backupId'] + '\nNative backup password: ' + key['password'] + '\nKeep this file separately from the encrypted .tar archive.\n').encode('utf8')
        await self.portal.recovery_kit(job, request['nonce'], kit)
        return True

    def purge_expired(self):
        # Only the temporary ciphertext expires. Preserve the unique native key
        # and owner mapping while the native encrypted backup still exists.
        for path in self.root.glob('*.json'):
            if path.name.endswith('.key.json'): continue
            state = read_private(path)
            if not state or state.get('phase') not in ('ready','cancelled_safe') or state.get('localExpiresAt') is None or state['localExpiresAt'] > self.clock(): continue
            export_id = state.get('job', {}).get('exportId')
            if not isinstance(export_id, str) or path.name != export_id + '.json': continue
            candidate = self.root / (export_id + '.tar')
            try: info = candidate.lstat()
            except FileNotFoundError: info = None
            if info is not None:
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077: raise ExportRejected('PRIVATE_FILE_UNSAFE')
                candidate.unlink()
            # Keep the reviewed terminal phase so maintenance guards accept it.
            state['downloaded'] = False
            state['localExpiresAt'] = None
            write_private(path, state)

    def busy(self):
        # Runtime update/restart handlers must ALSO check Supervisor's native backup job state.
        return any((read_private(p) or {}).get('phase') in ('planned', 'creating', 'created', 'uploading') for p in self.root.glob('*.json') if not p.name.endswith('.key.json'))

    def recovery_archive_context(self, backup_id, owner_scope):
        if not is_slug(backup_id) or not HEX.fullmatch(str(owner_scope)):
            return None
        for p in self.root.glob('*.json'):
            if p.name.endswith('.key.json'):
                continue
            s = read_private(p)
            if not s or s.get('phase') != 'ready' or s.get('job', {}).get('mode') != 'create_full' or s.get('job', {}).get('ownerScope') != owner_scope or s.get('backupId') != backup_id or not s.get('verified'):
                continue
            key = read_private(self.root / (s['job']['exportId'] + '.key.json'))
            if not key or key.get('imported') or key.get('bindingGeneration') != s['job']['bindingGeneration']:
                return None
            path = self.root / (s['job']['exportId'] + '.tar')
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except (FileNotFoundError, OSError):
                return None
            with os.fdopen(fd, 'rb') as f:
                info = os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                    return None
                digest = hashlib.file_digest(f, 'sha256').hexdigest()
            if info.st_mode & 0o077 or info.st_size != s['bytes'] or digest != s['sha256']:
                return None
            return {'backupId': backup_id, 'ownerScope': owner_scope, 'newBackup': True, 'password': key['password'], 'encrypted_path': str(path), 'sha256': digest, 'bytes': info.st_size,
                    'expected_addons': s['expectedAddons'], 'expected_folders': s['expectedFolders']}
        return None
