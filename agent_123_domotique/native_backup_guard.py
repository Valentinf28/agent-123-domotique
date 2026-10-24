"""Shared local maintenance barriers. No remote state is treated as proof of idle."""
import json
import os
from pathlib import Path
import stat
import re

EXPORT_DIRECTORY='native-backup-exports'
UPDATE_ACTIVE={'refreshing_catalog','backing_up','backup_uncertain','installing','awaiting_restart'}
RESET_ACTIVE={'backing_up','removing','partial','backup_uncertain'}

def _read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>1024*1024:raise ValueError()
        value=json.load(f)
        if not isinstance(value,dict):raise ValueError()
        return value

def local_maintenance_busy(data=Path('/data'), read_update=None):
    try:
        for filename,states,terminal in [('installation-update.json',UPDATE_ACTIVE,{'idle','prepared','completed','failed','attention_required','recovered'}),('installation-reset.json',RESET_ACTIVE,{'idle','prepared','completed','failed'}),('factory-stage.json',{'preparing','prepared','committing'},{'committed','failed','idle'})]:
            path=Path(data)/filename
            if path.exists():
                journal=_read(path);state=journal.get('state')
                if filename=='installation-update.json' and state=='attention_required' and journal.get('installSubmitted'):
                    entity=journal.get('entityId')
                    if not isinstance(entity,str) or not re.fullmatch(r'update\.[a-z0-9_]+',entity) or read_update is None:return True
                    native=read_update(entity)
                    if not isinstance(native,dict) or native.get('entity_id')!=entity or native.get('state') not in ('on','off') or native.get('attributes',{}).get('in_progress') is not False:return True
                if state in states or state not in terminal:return True
        return False
    except Exception:return True

def export_busy(data=Path('/data')):
    root=Path(data)/EXPORT_DIRECTORY
    try:
        if not root.exists():return False
        if root.is_symlink():return True
        for index,path in enumerate(root.glob('*.json')):
            if index>=1000:return True
            if path.name.endswith('.key.json'):continue
            phase=_read(path).get('phase')
            if phase not in {'ready','cancelled_safe','expired_safe','failed_safe'}:return True
        return False
    except Exception:return True

def native_backup_idle(read_backup):
    try:
        result=read_backup()
        if not isinstance(result,dict) or result.get('success') is False:return False
        data=result.get('result') if result.get('success') is True else result
        return isinstance(data,dict) and data.get('state')=='idle' and not data.get('agent_errors')
    except Exception:return False

def assert_update_ready(read_backup,data=Path('/data')):
    if export_busy(data) or not native_backup_idle(read_backup):
        raise RuntimeError('Attendez la fin de la sauvegarde avant de modifier cette installation.')

def worker_maintenance_busy(read_backup,data=Path('/data'),read_update=None):
    return local_maintenance_busy(data,read_update) or not native_backup_idle(read_backup)

def interrupts_backup(domain, service):
    return ((domain=='homeassistant' and service in {'restart','stop'})
            or (domain=='hassio' and service in {'addon_restart','addon_stop','addon_update','host_reboot','host_shutdown','restore_full','restore_partial'})
            or (domain=='update' and service=='install'))

from contextlib import contextmanager
import fcntl
@contextmanager
def guarded_system_action(read_backup,data=Path('/data')):
    path=Path(data)/'installation-maintenance.lock'
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_update_ready(read_backup,data)
        yield
