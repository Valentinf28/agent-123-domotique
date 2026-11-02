"""Offline boot-only preparation. No host services, networking or automatic reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

PROFILE = 'hdmi-maintenance-v2'
REQUIRED = ('quiet', 'loglevel=0', 'systemd.show_status=false', 'rd.systemd.show_status=false',
            'vt.global_cursor_default=0', 'systemd.mask=getty@tty1.service', 'systemd.mask=ha-cli@tty1.service',
            'systemd.mask=getty@.service', 'systemd.mask=autovt@.service', 'systemd.mask=ha-cli@.service')
MANAGED = {'quiet','loglevel','systemd.show_status','rd.systemd.show_status','vt.global_cursor_default'}
MACHINES = {'odroid-m1s', 'odroid-m1', 'odroid-n2'}

class Refused(Exception): pass

def sha(data): return hashlib.sha256(data).hexdigest()

def read_regular(path, limit=8192):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise Refused('fichier_non_conforme')
        data = stream.read(limit + 1)
        if len(data) > limit: raise Refused('fichier_trop_long')
        return data

def tokens(data):
    if len(data)>2047:raise Refused('cmdline_trop_longue')
    try: text = data.decode('ascii')
    except UnicodeError: raise Refused('format_cmdline_inconnu') from None
    line = text.removesuffix('\n').removesuffix('\r')
    if not line or any(ord(c) < 32 or ord(c) > 126 for c in line) or any(c in line for c in "\"'\\"):
        raise Refused('format_cmdline_inconnu')
    parts = line.split()
    if parts.count('console=tty0') != 1: raise Refused('console_hdmi_non_reconnue')
    if any(p.startswith(('systemd.unit=', 'rd.systemd.unit=', 'init=', 'rdinit=')) or p in ('debug','single','rescue','emergency') for p in parts):
        raise Refused('mode_demarrage_special')
    return parts

def target(data):
    parts = tokens(data)
    kept = [p for p in parts if p.split('=',1)[0] not in MANAGED and p not in REQUIRED]
    result = (' '.join(kept + list(REQUIRED)) + '\n').encode()
    if len(result)>2047:raise Refused('cmdline_trop_longue')
    return data if all(parts.count(p) == 1 for p in REQUIRED) and not any(p.split('=',1)[0] in MANAGED and p not in REQUIRED for p in parts) else result

def audit(data):
    parts = tokens(data)
    missing = [p for p in REQUIRED if parts.count(p) != 1]
    conflicts = [p.split('=',1)[0] for p in parts if p.split('=',1)[0] in MANAGED and p not in REQUIRED]
    return {'profile':PROFILE, 'parametersPresent':not missing and not conflicts,
            'missing':missing, 'conflictingKeys':conflicts, 'physicalValidationRequired':True}

def plan(root, machine, haos):
    if machine not in MACHINES or haos != '18.3': raise Refused('version_ou_carte_non_qualifiee')
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise Refused('partition_non_conforme')
    original = read_regular(root/'cmdline.txt'); proposed = target(original)
    return {'profile':PROFILE,'machine':machine,'haos':haos,'beforeSha256':sha(original),'afterSha256':sha(proposed),
            'changeRequired':original!=proposed,'onlyFile':'cmdline.txt','requiresReboot':original!=proposed,
            'hardwareValidated':False}

def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())

def replace_checked(path, expected, replacement):
    if read_regular(path) != expected: raise Refused('demarrage_modifie_depuis_controle')
    temporary = path.with_name('.labox-cmdline-' + secrets.token_hex(8) + '.tmp')
    try:
        private_write(temporary, replacement)
        if read_regular(temporary) != replacement: raise Refused('verification_ecriture_echouee')
        if read_regular(path) != expected: raise Refused('demarrage_modifie_depuis_controle')
        os.replace(temporary, path); sync_directory(path.parent)
        if read_regular(path) != replacement: raise Refused('verification_ecriture_echouee')
    finally:
        if temporary.exists(): temporary.unlink()

def apply(root, backups, machine, haos, expected, device_id):
    if not re.fullmatch('[a-f0-9]{64}', expected) or not re.fullmatch('[a-zA-Z0-9-]{8,64}', device_id):
        raise Refused('confirmation_invalide')
    report = plan(root,machine,haos)
    if report['beforeSha256'] != expected: raise Refused('demarrage_modifie_depuis_controle')
    if not report['changeRequired']: return {**report,'changed':False,'backup':None}
    backups = Path(backups)
    if not backups.is_dir() or backups.is_symlink() or backups.resolve().is_relative_to(Path(root).resolve()):
        raise Refused('destination_sauvegarde_invalide')
    original=read_regular(Path(root)/'cmdline.txt'); proposed=target(original)
    if sha(original)!=expected or sha(proposed)!=report['afterSha256']:raise Refused('demarrage_modifie_depuis_controle')
    folder=backups/('hdmi-'+secrets.token_hex(12));folder.mkdir(mode=0o700)
    receipt={**report,'deviceId':device_id,'backupFormat':1}
    private_write(folder/'cmdline.original',original)
    private_write(folder/'receipt.json',(json.dumps(receipt,sort_keys=True)+'\n').encode())
    sync_directory(folder);sync_directory(backups)
    # Recheck the durable backup before touching boot. No repair from guessed defaults.
    if read_regular(folder/'cmdline.original') != original: raise Refused('sauvegarde_non_confirmee')
    replace_checked(Path(root)/'cmdline.txt',original,proposed)
    return {**report,'changed':True,'backup':str(folder)}

def restore(root, backup, expected, device_id):
    backup=Path(backup)
    if backup.is_symlink() or not backup.is_dir(): raise Refused('sauvegarde_non_conforme')
    receipt=json.loads(read_regular(backup/'receipt.json'))
    original=read_regular(backup/'cmdline.original');current=read_regular(Path(root)/'cmdline.txt')
    if (receipt.get('backupFormat')!=1 or receipt.get('profile')!=PROFILE or receipt.get('deviceId')!=device_id
            or sha(original)!=receipt.get('beforeSha256') or sha(target(original))!=receipt.get('afterSha256')):
        raise Refused('sauvegarde_non_conforme')
    if sha(current)!=expected or expected!=receipt['afterSha256']:
        raise Refused('restauration_refusee_demarrage_modifie')
    replace_checked(Path(root)/'cmdline.txt',current,original)
    return {'restored':True,'sha256':sha(original),'requiresReboot':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Préparer le masquage HDMI HAOS sur une partition montée en atelier.')
    parser.add_argument('operation',choices=['plan','apply','restore','audit'])
    parser.add_argument('--boot',required=True);parser.add_argument('--machine',default='odroid-m1s');parser.add_argument('--haos',default='18.3')
    parser.add_argument('--expected-sha256',default='');parser.add_argument('--device-id',default='');parser.add_argument('--backups');parser.add_argument('--backup')
    args=parser.parse_args()
    try:
        if args.operation=='plan':result=plan(args.boot,args.machine,args.haos)
        elif args.operation=='apply':result=apply(args.boot,args.backups,args.machine,args.haos,args.expected_sha256,args.device_id)
        elif args.operation=='restore':result=restore(args.boot,args.backup,args.expected_sha256,args.device_id)
        else:result=audit(read_regular(Path(args.boot)/'cmdline.txt'))
        print(json.dumps(result,ensure_ascii=False))
    except (Refused,OSError,ValueError,TypeError) as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,Refused) else 'preparation_refusee'}));raise SystemExit(1)
