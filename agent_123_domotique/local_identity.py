"""Local, read-only proof of box identity. No credential or control endpoint."""
import json
import os
import re
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from network_discovery import current_adapters, local_interfaces

ENTITY = 'sensor.1_2_3_home_local_identity'
PORT = 18423

def load_key(path):
    path = Path(path)
    if path.exists():
        return Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    key = Ed25519PrivateKey.generate()
    data = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return key

def valid_origin(origin, addresses):
    try:
        parsed = urlsplit(origin)
        if parsed.scheme != 'http' or parsed.port not in (None, 80, 8123) or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        if parsed.hostname in addresses:
            return True
        if parsed.hostname and parsed.hostname.endswith('.local'):
            return any(row[4][0] in addresses for row in socket.getaddrinfo(parsed.hostname, None, socket.AF_INET))
    except (ValueError, OSError):
        pass
    return False

def proof(key, nonce, origin, addresses):
    if not re.fullmatch('[a-f0-9]{64}', nonce) or not valid_origin(origin, addresses):
        raise ValueError('Invalid local challenge')
    message = f'123home-local-v1\n{nonce}\n{origin}'
    return {'signature': key.sign(message.encode('ascii')).hex()}

def serve(call, path='/data/local-identity.key'):
    key = load_key(path)
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    def publish():
        while True:
            try:
                call('/states/' + ENTITY, method='POST', payload={
                    'state': 'ready', 'attributes': {'public_key': public, 'protocol': 1}})
            except Exception:
                pass
            time.sleep(60)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)
        def log_message(self, *args):
            pass
        def do_GET(self):
            try:
                parts = urlsplit(self.path)
                if parts.path != '/identity' or len(self.path) > 512:
                    raise ValueError()
                args = parse_qs(parts.query, strict_parsing=True)
                if set(args) != {'nonce', 'origin'} or any(len(v) != 1 for v in args.values()):
                    raise ValueError()
                addresses = {str(i.ip) for i in local_interfaces(current_adapters([]))}
                result = proof(key, args['nonce'][0], args['origin'][0], addresses)
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (ValueError, OSError):
                self.send_error(400)
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    threading.Thread(target=publish, daemon=True).start()
    server.serve_forever()
