"""Optional temporary workshop worker. Exact device + PARTUUID, no network or host PID."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from boot import Refused,apply,audit,plan,read_regular,restore

MOUNT=Path('/tmp/labox-boot')

def command(args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=15).stdout.strip()

def device_info(path,partuuid):
    if (not re.fullmatch(r'/dev/(mmcblk[0-9]+p[0-9]+|sd[a-z]+[0-9]+|nvme[0-9]+n[0-9]+p[0-9]+)',path)
            or not re.fullmatch('[a-fA-F0-9-]{8,64}',partuuid)):
        raise Refused('partition_a_identifier')
    if os.path.realpath(path)!=path or not stat.S_ISBLK(os.stat(path).st_mode):raise Refused('peripherique_non_conforme')
    data={}
    for line in command(['blkid','-p','-o','export',path]).splitlines():
        key,_,value=line.partition('=');data[key]=value
    if data.get('TYPE')!='vfat' or data.get('LABEL')!='hassos-boot' or data.get('PART_ENTRY_UUID','').lower()!=partuuid.lower():
        raise Refused('partition_de_demarrage_non_confirmee')
    return data

def main():
    options=json.loads(Path('/data/options.json').read_text())
    operation=options.get('operation','plan')
    if operation not in ('plan','apply','restore'):raise Refused('operation_invalide')
    path=options.get('device','');partuuid=options.get('partuuid','');device_info(path,partuuid)
    MOUNT.mkdir(mode=0o700,exist_ok=True)
    if MOUNT.is_symlink() or os.path.ismount(MOUNT) or any(MOUNT.iterdir()):raise Refused('point_montage_occupe')
    readonly=operation=='plan'
    flags=('ro' if readonly else 'rw')+',sync,fmask=0022,dmask=0022,codepage=437,iocharset=iso8859-1,shortname=mixed,utf8,errors=remount-ro'
    environment=dict(os.environ,LIBMOUNT_FORCE_MOUNT2='always')
    subprocess.run(['mount','-t','vfat','-o',flags,path,str(MOUNT)],check=True,env=environment,capture_output=True,timeout=15)
    try:
        device_info(path,partuuid)
        if operation=='plan':result=plan(MOUNT,options['machine'],options['haos'])
        elif operation=='apply':
            backups=Path('/share/labox-boot-backups');backups.mkdir(mode=0o700,exist_ok=True)
            result=apply(MOUNT,backups,options['machine'],options['haos'],options['expected_sha256'],partuuid)
        else:
            backup=options.get('backup','')
            if not re.fullmatch('/share/labox-boot-backups/hdmi-[a-f0-9]{24}',backup):raise Refused('sauvegarde_non_conforme')
            result=restore(MOUNT,backup,options['expected_sha256'],partuuid)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:subprocess.run(['umount',str(MOUNT)],check=True,capture_output=True,timeout=15)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,Refused) else 'preparation_refusee','rebootTriggered':False}),flush=True)
        raise SystemExit(1)
