"""Optional workshop-armed app. Unavailable lifecycle marker always fails closed."""
import asyncio
import fcntl
from pathlib import Path
import signal
import time
from access_point import AccessPoint
from controller import Controller
from http_setup import HTTP
from model import Lifecycle, Refused, read
from network import Network

MARKER = '/homeassistant_config/.labox-network-bootstrap.json'

async def run():
    options = read('/data/options.json')
    life = Lifecycle('/data/onboarding.json')
    def marker():
        p = Path(MARKER)
        if not p.exists() or abs(time.time() - p.stat().st_mtime) > 30:
            raise Refused('etat_box_non_confirme')
        return read(p)
    eligible = False
    if options.get('armed'):
        # Agent starts after services; wait for its fresh local lifecycle proof.
        for _ in range(120):
            try:
                initial = marker(); break
            except (Refused, OSError, ValueError): await asyncio.sleep(5)
        else: raise Refused('etat_box_non_confirme')
        eligible = life.prepare(options, initial)
    elif not life.data:
        return  # A disabled, never-prepared unit performs no network operations.
    if not life.data.get('mac'): return
    network = Network(); await network.connect(); await network.select(life.data['mac'])
    access = AccessPoint(network.interface)
    controller = Controller(life, network, marker, options)
    server = None; ui = None
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if life.data.get("boot_id") != boot_id or life.data.get("nm_owner") != network.destination:
            life.save(checkpoint="", guard="")  # NM checkpoints do not survive a host reboot.
        life.save(nm_owner=network.destination)
        await controller.recover()
        life.new_boot(boot_id)
        previous_interface = life.data.get("firewall_interface")
        if previous_interface and previous_interface != network.interface:
            AccessPoint(previous_interface).stop()
        access.stop()  # Remove stale private chains left by an interrupted previous container.
        if not eligible: return
        while not stop.is_set():
            if await controller.allowed():
                # Firewall precedes radio activation; a setup client cannot reach HA or the agent.
                life.save(firewall_interface=network.interface)
                access.firewall()
                if not await controller.open_ap(): break
                access.start_dns(); await asyncio.sleep(.3)
                if not access.healthy(): raise Refused('service_local_indisponible')
                ui = HTTP(controller); server = await ui.listen()
                while not stop.is_set():
                    await asyncio.sleep(1)
                    if life.data['phase'] == 'complete': return
                    if not access.healthy(): raise Refused('service_local_indisponible')
                    if not controller.lock.locked():
                        if not controller.available and life.data['phase'] != 'queued': raise Refused('retour_reseau_a_verifier')
                        if not await controller.allowed(): return
                return
            if life.data.get('phase') in ('complete', 'retired', 'expired'): return
            try: await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError: pass
    finally:
        if server: server.close(); await server.wait_closed()
        if ui:
            for task in ui.tasks: task.cancel()
            await asyncio.gather(*list(ui.tasks), return_exceptions=True)
        # AP removal must succeed before removing isolation. Fail closed on D-Bus failure.
        await controller.close()
        access.stop()
        if network.bus: network.bus.disconnect()

if __name__ == '__main__':
    Path('/data').mkdir(exist_ok=True)
    with open('/data/onboarding.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: asyncio.run(run())
        except Exception as exc:
            # Fixed codes only, never raw D-Bus/HTTP/credentials exceptions.
            print('Configuration Wi-Fi en attente : ' + (str(exc) if isinstance(exc, Refused) else 'verification_atelier_requise'), flush=True)
