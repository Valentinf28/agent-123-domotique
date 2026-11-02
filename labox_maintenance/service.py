"""Local-only authenticated recovery console; disabled until individually provisioned."""
import asyncio
import fcntl
import json
from pathlib import Path
import signal
from host import Host
from security import Attempts,Refused,valid_configuration
from session import Session
from terminal import Terminal

async def run():
    options=json.loads(Path('/data/options.json').read_text())
    if options.get('enabled') is not True:return
    host=Host();await host.connect();valid_configuration(options,await host.machine_id())
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    attempts=Attempts('/data/attempts.json',boot_id)
    session=Session(options,host,attempts);tty=Terminal(options["machine_id"],boot_id);stopping=asyncio.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):asyncio.get_running_loop().add_signal_handler(sig,stopping.set)
    try:
        # A previously authenticated native session retains its independent host timeout.
        while await host.state() not in ('inactive','failed'):
            if stopping.is_set():return
            await asyncio.sleep(1)
        for unit in ('ha-cli@tty8.service','getty@tty8.service'):
            if await host.state(unit) not in ('inactive','failed'):raise Refused('console_technique_occupee')
        for unit in ('getty@tty8.service','autovt@tty8.service','ha-cli@tty8.service'):
            if not await host.masked(unit):raise Refused('profil_boot_maintenance_a_appliquer')
        tty.open()
        while not stopping.is_set():
            vt=tty.active()
            if vt!=8:
                if 1<=vt<=7:tty.return_vt=vt
                await asyncio.sleep(.3);continue
            tty.prompt()
            remaining=attempts.remaining()
            if remaining:
                tty.write(f'\r\nAttendre {remaining} s avant un nouvel essai.\r\n')
                await asyncio.sleep(min(remaining,2));continue
            code=await tty.read_code()
            if code is None:continue
            try:
                await session.open(code,tty.return_vt,before_start=tty.handoff)
                # StartTransientUnit queues a job; wait for its actual terminal owner.
                for _ in range(30):
                    if await host.state() in ('active','activating'):break
                    await asyncio.sleep(.1)
                while await host.state() in ('active','activating','deactivating'):
                    if stopping.is_set():await host.stop();return
                    await asyncio.sleep(1)
            except Refused:
                if tty.fd is None:
                    await host.stop();tty.open()
                tty.prompt();tty.write('\r\nAcces refuse ou session indisponible.\r\n');await asyncio.sleep(2)
            finally:
                code=None
                if tty.fd is None and not stopping.is_set():
                    await host.stop();tty.open()
    finally:
        # Stop only this fixed native session, never getty, kiosk, HA or other host services.
        try:await host.stop()
        finally:tty.close();host.bus.disconnect()

if __name__=='__main__':
    with open('/data/maintenance.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:asyncio.run(run())
        except Exception as exc:print('Maintenance locale fermee : '+(str(exc) if isinstance(exc,Refused) else 'verification_atelier_requise'),flush=True)
