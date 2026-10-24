"""Box wiring for the isolated native backup worker; no blocking heartbeat I/O."""
import asyncio
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from native_backup_export import NativeBackupExportWorker, ExportRejected, read_private
from native_backup_transport import PortalBackupTransport, SupervisorBackupTransport
from native_backup_guard import EXPORT_DIRECTORY, worker_maintenance_busy
from recovery_archive_binding import make_recovery_verifier

class NativeBackupRuntime:
    def __init__(self, portal_url, credential, supervisor_credential, read_native_backup, *, read_native_update=None, data=Path('/data'), report=None):
        parsed=urlsplit(portal_url)
        if parsed.path not in ('','/','/api') or parsed.query or parsed.fragment:
            raise ValueError('Unsupported backup portal origin')
        origin=parsed.scheme+'://'+parsed.netloc
        self.data=Path(data)
        self.report=report or (lambda _message:None)
        async def maintenance_busy():
            return await asyncio.to_thread(worker_maintenance_busy,read_native_backup,self.data,read_native_update)
        self.worker=NativeBackupExportWorker(self.data/EXPORT_DIRECTORY,
                    SupervisorBackupTransport(supervisor_credential),PortalBackupTransport(origin,credential),
                    maintenance_lock=self.data/'installation-maintenance.lock',maintenance_busy=maintenance_busy)
        self.recovery_verifier=make_recovery_verifier(self.worker.recovery_archive_context,self.data/EXPORT_DIRECTORY)
        self._lock=threading.Lock();self._thread=None;self._job=None
        # A cancelled/rotated server job may disappear from the next heartbeat.
        # Retain the native pending operation until its status is reconciled.
        for path in sorted((self.data/EXPORT_DIRECTORY).glob('*.json')):
            if path.name.endswith('.key.json'):continue
            saved=read_private(path)
            if saved and saved.get('phase') in ('planned','creating','created','uploading'):
                self._job=saved.get('job');break

    def submit(self, job):
        with self._lock:
            if isinstance(job,dict) and (not isinstance(self._job,dict) or self._job.get('exportId')==job.get('exportId')):
                self._job=json.loads(json.dumps(job))
            if not isinstance(self._job,dict):return
            if self._thread is not None and self._thread.is_alive():return
            snapshot=json.loads(json.dumps(self._job))
            self._thread=threading.Thread(target=self._run,args=(snapshot,),daemon=True,name='native-backup-export')
            self._thread.start()

    def _run(self, job):
        try:
            with self.worker.locked() as acquired:
                if acquired:self.worker.purge_expired()
            asyncio.run(self.worker.tick(job))
        except ExportRejected:
            self.report('Copie locale en attente de vérification ; aucun nouvel ordre de sauvegarde automatique.')
        except Exception:
            self.report('Copie locale interrompue ; reprise vérifiée au prochain échange.')
        finally:
            try:
                saved=read_private(self.data/EXPORT_DIRECTORY/(job['exportId']+'.json'))
                if saved and saved.get('phase') in ('ready','cancelled_safe','expired_safe','failed_safe'):
                    with self._lock:
                        if self._job and self._job.get('exportId')==job['exportId']:self._job=None
            except Exception:pass
