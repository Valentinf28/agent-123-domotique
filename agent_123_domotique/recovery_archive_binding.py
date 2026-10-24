"""Bind native SecureTar validation to a newly-created, privately held backup."""
import os
from pathlib import Path
import re
import stat
from recovery_securearchive import verify_archive, ArchiveRejected

def make_recovery_verifier(context_provider, private_root):
    root=Path(private_root).absolute()
    def verify(backup_id, owner_scope, addon):
        fd=None
        try:
            if not re.fullmatch(r'[a-f0-9]{64}',owner_scope):raise ValueError()
            context=context_provider(backup_id,owner_scope)
            if (not isinstance(context,dict) or context.get('backupId')!=backup_id
                    or context.get('ownerScope')!=owner_scope or context.get('newBackup') is not True):raise ValueError()
            path=Path(context['encrypted_path']).absolute()
            if not path.is_relative_to(root) or path==root:raise ValueError()
            # No indirect directory/file targets, even when they resolve in-root.
            for directory in [root,*path.relative_to(root).parents]:
                candidate=directory if directory.is_absolute() else root/directory
                if candidate.is_symlink():raise ValueError()
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                    or stat.S_IMODE(before.st_mode)!=0o600 or before.st_size!=context['bytes']):raise ValueError()
            with os.fdopen(fd,'rb') as stream:
                fd=None
                result=verify_archive(stream,context['password'],backup_id,addon,
                                      expected_addons=context['expected_addons'],expected_folders=context['expected_folders'])
                after=os.fstat(stream.fileno())
            if (result['sha256']!=context['sha256'] or result['bytes']!=context['bytes']
                    or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns)):raise ValueError()
            current=context_provider(backup_id,owner_scope)
            for key in ('backupId','ownerScope','newBackup','encrypted_path','sha256','bytes'):
                if current.get(key)!=context.get(key):raise ValueError()
            return result|{'ownerScope':owner_scope,'newBackup':True}
        except Exception:
            raise ArchiveRejected('La preuve privée de cette nouvelle sauvegarde est indisponible.') from None
        finally:
            if fd is not None:os.close(fd)
    return verify
