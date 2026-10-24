"""Persistent lifecycle. No network side effects and no customer Wi-Fi password on disk."""
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import time
import uuid

IP = '192.168.77.1'
NETWORK = ipaddress.ip_network('192.168.77.0/24')
PORT = 18424
WINDOW = 900

class Refused(Exception):
    pass

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)

def read(path):
    return json.loads(Path(path).read_text())

def validate_options(value):
    if type(value.get('armed')) is not bool:
        raise Refused('configuration_invalide')
    if not value['armed']:
        return
    if not re.fullmatch('[a-f0-9]{64}', value.get('factory_context', '')):
        raise Refused('preparation_atelier_requise')
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', value.get('wifi_mac', '')):
        raise Refused('cle_wifi_a_identifier')

def credentials(ssid, password):
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
        raise Refused('nom_wifi_invalide')
    if not isinstance(password, str) or not ((8 <= len(password) <= 63 and password.isascii() and all(32 <= ord(c) <= 126 for c in password)) or re.fullmatch('[0-9a-fA-F]{64}', password)):
        raise Refused('mot_de_passe_invalide')
    return ssid, password

class Lifecycle:
    def __init__(self, path):
        self.path = Path(path)
        self.data = read(path) if self.path.exists() else {}

    def save(self, **values):
        self.data.update(values); atomic(self.path, self.data)

    def prepare(self, options, marker):
        validate_options(options)
        if marker.get('installed') is True:
            self.save(phase='retired', error=''); return False
        if not options['armed']:
            return False
        context = options['factory_context']
        if marker.get('version') != 1 or marker.get('prepared') is not True or marker.get('factoryContext') != context:
            raise Refused('preparation_atelier_non_confirmee')
        if self.data and self.data.get('context') != context:
            # A new factory identity must be deliberately prepared, never adopted in the field.
            raise Refused('nouvelle_preparation_atelier_requise')
        if not self.data:
            self.save(context=context, mac=options['wifi_mac'].upper(), phase='ready',
                      ssid='LaBox-' + secrets.token_hex(3).upper(), psk=secrets.token_hex(10),
                      ap_uuid=str(uuid.uuid4()), deadline=0, error='')
        if self.data.get('mac') != options['wifi_mac'].upper():
            raise Refused('cle_wifi_differente')
        return self.data['phase'] not in ('complete', 'retired')

    def gate(self, marker, snapshot, now=None):
        now = time.monotonic() if now is None else now
        if marker.get('installed') is True:
            self.save(phase='retired', error=''); return False
        if (marker.get('version') != 1 or marker.get('factoryContext') != self.data.get('context')
                or marker.get('prepared') is not True):
            raise Refused('preparation_atelier_non_confirmee')
        if self.data.get('phase') in ('complete', 'retired', 'expired'):
            return False
        if snapshot['foreign_wifi']:
            self.save(phase='retired', error='wifi_deja_configure'); return False
        if snapshot['ethernet']:
            return False
        if not snapshot['ap_capable']:
            raise Refused('cle_wifi_non_compatible_point_acces')
        if snapshot.get('busy'):
            raise Refused('interface_wifi_occupee')
        if any(ipaddress.ip_network(n, strict=False).overlaps(NETWORK) for n in snapshot.get('networks', [])):
            raise Refused('conflit_adresse_locale')
        if self.data.get('deadline') and now >= self.data['deadline']:
            self.save(phase='expired', error='delai_ecoule'); return False
        return True

    def new_boot(self, boot_id):
        if self.data.get("phase") in ("complete", "retired"):
            return
        if self.data.get("boot_id") != boot_id:
            self.save(boot_id=boot_id, deadline=0, phase="ready")

    def opening(self):
        if not self.data.get('deadline'):
            self.save(deadline=time.monotonic() + WINDOW)
        self.save(phase='hotspot')

    def public(self, networks):
        return {'phase': self.data.get('phase', 'unprepared'), 'error': self.data.get('error', ''),
                'remaining': max(0, int(self.data.get('deadline', 0) - time.monotonic())), 'networks': networks}
