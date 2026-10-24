"""Single-radio first-boot transaction, protected by host-owned NM checkpoint."""
import asyncio
import time
import uuid
from model import Refused, credentials
from network import profile, portal_reachable

class Controller:
    def __init__(self, lifecycle, backend, marker, options, *, probe=portal_reachable):
        self.life = lifecycle; self.net = backend; self.marker = marker; self.options = options
        self.probe = probe; self.lock = asyncio.Lock(); self.networks = []; self.available = False

    def owned(self):
        return {s for s in (self.life.data.get('ap_uuid'), self.life.data.get('candidate')) if s}

    async def allowed(self):
        return self.life.gate(self.marker(), await self.net.snapshot(self.owned(), self.life.data['mac']))

    async def recover(self):
        """Abort any interrupted test; never infer success from a stale journal."""
        d = self.life.data
        if d.get('checkpoint'): await self.net.rollback(d['checkpoint'])
        if d.get('guard'): await self.net.rollback(d['guard'])
        # If complete, keep the proven station profile. Otherwise remove only our candidate.
        if d.get('candidate') and d.get('phase') != 'complete' and not d.get('provisioned'):
            await self.net.remove(d['candidate'])
        await self.net.remove(d['ap_uuid'])
        if d.get('phase') in ('testing', 'hotspot', 'committing', 'queued'):
            self.life.save(phase='ready', checkpoint='', guard='', candidate='', error='tentative_interrompue')

    async def open_ap(self):
        if not await self.allowed(): return False
        self.networks = await self.net.scan()
        # Recheck after scan: a cable or installation may have appeared meanwhile.
        if not await self.allowed(): return False
        d = self.life.data
        await self.net.remove(d['ap_uuid'])
        self.life.opening()
        guard = await self.net.checkpoint(timeout=max(1, int(d['deadline'] - time.monotonic())))
        self.life.save(guard=guard)
        path = await self.net.add(profile(d['ap_uuid'], d['mac'], d['ssid'], d['psk'], hotspot=True))
        await self.net.activate(path)
        await self.net.wait_ap(d['ap_uuid'])
        self.life.opening(); self.available = True
        return True

    def reserve(self, ssid, password):
        credentials(ssid, password)
        if not self.available or self.life.data.get('phase') != 'hotspot' or self.lock.locked():
            raise Refused('connexion_deja_en_cours')
        self.available = False
        self.life.save(phase='queued')
        return ssid, password

    async def attempt(self, ssid, password):
        async with self.lock:
            checkpoint = ''; candidate = str(uuid.uuid4())
            try:
                async with asyncio.timeout(110):
                    if not await self.allowed(): raise Refused('configuration_non_autorisee')
                    # Checkpoint must exist BEFORE any activation replaces the temporary AP.
                    if self.life.data['deadline'] - time.monotonic() < 160:
                        raise Refused('delai_insuffisant_redemarrez')
                    checkpoint = await self.net.checkpoint(guard=self.life.data['guard'])
                    self.life.save(phase='testing', checkpoint=checkpoint, candidate=candidate, error='')
                    settings = profile(candidate, self.life.data['mac'], ssid, password)
                    path = await self.net.add(settings)
                    await self.net.activate(path)
                    await self.net.wait_ip(candidate)
                    if self.marker().get('installed') or (await self.net.snapshot(self.owned(), self.life.data['mac']))['ethernet']:
                        raise Refused('configuration_modifiee_pendant_essai')
                    reachable = await asyncio.wait_for(asyncio.to_thread(self.probe, self.net.interface), timeout=15)
                    if not reachable: raise Refused('internet_non_confirme')
                    # Persist before releasing autonomous rollback. A crash here rolls back and
                    # startup removes this exact candidate; it cannot become a false success.
                    self.life.save(phase='committing')
                    await self.net.persist(path, settings)
                    await self.net.destroy(checkpoint)
                    await self.net.destroy(self.life.data['guard'])
                    self.life.save(phase='complete', checkpoint='', guard='', error='', provisioned=True)
            except Exception as exc:
                code = str(exc) if isinstance(exc, Refused) else 'connexion_non_confirmee'
                # Do NOT swallow a rollback error and claim the AP is usable.
                if checkpoint: await self.net.rollback(checkpoint)
                await self.net.remove(candidate)
                self.life.save(phase='hotspot', checkpoint='', candidate='', error=code)
                if not checkpoint:
                    self.available = await self.allowed()
                    return
                if await self.allowed():
                    if not await self.net.guard_valid(self.life.data.get('guard', '')):
                        raise Refused('delai_ecoule')
                    d = self.life.data
                    path = await self.net.add(profile(d['ap_uuid'], d['mac'], d['ssid'], d['psk'], hotspot=True)) if not await self._ap_exists() else await self._ap_path()
                    await self.net.activate(path); await self.net.wait_ap(d['ap_uuid'])
                    self.available = True
            finally:
                # Secret stays in this call's memory only; no durable journal/log/API response.
                password = None

    async def _ap_path(self):
        for path, p in await self.net.profiles():
            if p.get('connection', {}).get('uuid') == self.life.data['ap_uuid']: return path
        raise Refused('point_acces_non_demarre')

    async def _ap_exists(self):
        return any(p.get('connection', {}).get('uuid') == self.life.data['ap_uuid'] for _, p in await self.net.profiles())

    async def close(self):
        self.available = False
        if self.life.data.get('checkpoint'): await self.net.rollback(self.life.data['checkpoint'])
        if self.life.data.get('guard'): await self.net.rollback(self.life.data['guard'])
        await self.net.remove(self.life.data['ap_uuid'])
