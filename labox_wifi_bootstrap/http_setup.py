"""Small bounded HTTP service, only bound to the AP address; no CORS or cloud assets."""
import asyncio
from collections import deque
import ipaddress
import json
from pathlib import Path
import secrets
import time
from model import IP, NETWORK, PORT, Refused

ORIGIN = f'http://{IP}:{PORT}'

class HTTP:
    def __init__(self, controller):
        self.controller = controller; self.token = secrets.token_urlsafe(32)
        self.slots = asyncio.Semaphore(8); self.requests = deque(); self.attempts = deque()
        self.tasks = set()

    @staticmethod
    def limit(queue, count):
        now = time.monotonic()
        while queue and queue[0] <= now - 60: queue.popleft()
        if len(queue) >= count: raise Refused('trop_de_demandes')
        queue.append(now)

    def authorize(self, peer, method, target, headers):
        if ipaddress.ip_address(peer) not in NETWORK or peer == IP: raise Refused('acces_refuse')
        self.limit(self.requests, 180)
        host = headers.get('host', '')
        if host != f'{IP}:{PORT}':
            if method == 'GET' and not target.startswith('/api/'):
                return False  # Captive detection gets redirected; never accepts a foreign Host API.
            raise Refused('acces_refuse')
        if method == 'POST':
            if (headers.get('origin') != ORIGIN or headers.get('x-setup-token') != self.token
                    or headers.get('content-type') != 'application/json'):
                raise Refused('acces_refuse')
        return True

    async def reply(self, writer, status, body, content='application/json; charset=utf-8', extra=None):
        if not isinstance(body, bytes): body = json.dumps(body).encode()
        headers = {'Content-Type': content, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
            'Connection': 'close', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
        headers.update(extra or {})
        writer.write((f'HTTP/1.1 {status}\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) + '\r\n').encode() + body)
        await writer.drain()

    async def delayed_attempt(self, ssid, password):
        await asyncio.sleep(2)  # Deliver instructions before the single radio changes networks.
        await self.controller.attempt(ssid, password)

    def done(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            self.controller.available = False  # Runtime watchdog closes the AP on rollback failure.

    async def handle(self, reader, writer):
        task_payload = None
        try:
            if self.slots.locked(): raise Refused('trop_de_demandes')
            async with self.slots:
                raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=4)
                if len(raw) > 8192: raise Refused('requete_invalide')
                lines = raw.decode('ascii').split('\r\n')
                method, target, protocol = lines[0].split(' ')
                if protocol != 'HTTP/1.1' or method not in ('GET', 'POST'): raise Refused('requete_invalide')
                headers = {}
                for line in lines[1:]:
                    if not line: continue
                    key, value = line.split(':', 1); key = key.lower()
                    if key in headers or key.strip() != key: raise Refused('requete_invalide')
                    headers[key] = value.strip()
                if 'transfer-encoding' in headers: raise Refused('requete_invalide')
                if not self.authorize(writer.get_extra_info('peername')[0], method, target, headers):
                    await self.reply(writer, '302 Found', b'', extra={'Location': ORIGIN + '/'}); return
                if method == 'GET':
                    if headers.get('content-length', '0') != '0': raise Refused('requete_invalide')
                    if target == '/api/status':
                        await self.reply(writer, '200 OK', self.controller.life.public(self.controller.networks))
                    elif target == '/api/session':
                        await self.reply(writer, '200 OK', {'token': self.token})
                    elif target in ('/', '/style.css', '/setup.js'):
                        name = {'/': 'index.html', '/style.css': 'style.css', '/setup.js': 'setup.js'}[target]
                        types = {'index.html': 'text/html; charset=utf-8', 'style.css': 'text/css', 'setup.js': 'text/javascript'}
                        await self.reply(writer, '200 OK', (Path(__file__).parent / 'web' / name).read_bytes(), types[name])
                    else: await self.reply(writer, '302 Found', b'', extra={'Location': ORIGIN + '/'})
                elif target == '/api/connect':
                    self.limit(self.attempts, 3)
                    size = int(headers.get('content-length', '0'))
                    if not 1 <= size <= 1024: raise Refused('requete_invalide')
                    value = json.loads(await asyncio.wait_for(reader.readexactly(size), timeout=4))
                    if not isinstance(value, dict) or set(value) != {'ssid', 'password'}: raise Refused('requete_invalide')
                    task_payload = self.controller.reserve(value['ssid'], value['password'])
                    await self.reply(writer, '202 Accepted', {'phase': 'testing', 'retryAfter': 150})
                else: raise Refused('requete_invalide')
        except Exception as exc:
            try: await self.reply(writer, '400 Bad Request', {'error': str(exc) if isinstance(exc, Refused) else 'requete_invalide'})
            except (OSError, ConnectionError): pass
        finally:
            writer.close()
            if task_payload:
                task = asyncio.create_task(self.delayed_attempt(*task_payload)); self.tasks.add(task); task.add_done_callback(self.done)

    async def listen(self):
        return await asyncio.start_server(self.handle, IP, PORT, limit=8192)
