"""Narrow NetworkManager D-Bus adapter. Never calls nmcli or edits HAOS files."""
import asyncio
import http.client
import ipaddress
import re
import socket
import ssl
import uuid
from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from model import IP, Refused

DEST = 'org.freedesktop.NetworkManager'
ROOT = '/org/freedesktop/NetworkManager'
SETTINGS = ROOT + '/Settings'
DEV = DEST + '.Device'
WIFI = DEV + '.Wireless'
CONN = DEST + '.Settings.Connection'
ACTIVE = DEST + '.Connection.Active'

def unwrap(v):
    if isinstance(v, Variant): return unwrap(v.value)
    if isinstance(v, dict): return {k: unwrap(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [unwrap(x) for x in v]
    return v

def profile(identity, mac, ssid, password, *, hotspot=False):
    # Explicit MAC binding survives USB interface-name changes.
    wireless = {'ssid': Variant('ay', ssid.encode()), 'mode': Variant('s', 'ap' if hotspot else 'infrastructure'),
                'mac-address': Variant('ay', bytes.fromhex(mac.replace(':', ''))),
                'cloned-mac-address': Variant('s', 'permanent'), 'powersave': Variant('u', 2)}
    if hotspot:
        wireless.update({'band': Variant('s', 'bg'), 'channel': Variant('u', 6), 'ap-isolation': Variant('i', 1)})
    return {
        'connection': {'id': Variant('s', 'labox-setup-' + identity), 'uuid': Variant('s', identity),
                       'type': Variant('s', '802-11-wireless'), 'autoconnect': Variant('b', False)},
        '802-11-wireless': wireless,
        '802-11-wireless-security': {'key-mgmt': Variant('s', 'wpa-psk'), 'psk': Variant('s', password),
                                    'psk-flags': Variant('u', 0), 'proto': Variant('as', ['rsn']),
                                    'pairwise': Variant('as', ['ccmp']), 'group': Variant('as', ['ccmp'])},
        'ipv4': ({'method': Variant('s', 'manual'), 'never-default': Variant('b', True),
                  'address-data': Variant('aa{sv}', [{'address': Variant('s', IP), 'prefix': Variant('u', 24)}])}
                 if hotspot else {'method': Variant('s', 'auto'), 'dhcp-timeout': Variant('i', 35)}),
        'ipv6': {'method': Variant('s', 'disabled')},
    }

class Network:
    def __init__(self):
        self.bus = None; self.device = None; self.interface = None; self.destination = DEST

    async def connect(self, address='unix:path=/run/dbus/system_bus_socket'):
        self.bus = await MessageBus(bus_address=address).connect()
        reply = await asyncio.wait_for(self.bus.call(Message(destination='org.freedesktop.DBus',
            path='/org/freedesktop/DBus', interface='org.freedesktop.DBus', member='GetNameOwner',
            signature='s', body=[DEST])), timeout=5)
        if reply.message_type == MessageType.ERROR: raise Refused('service_reseau_indisponible')
        self.destination = reply.body[0]  # Never send a stale transaction to a restarted NM daemon.

    async def call(self, path, iface, member, signature='', body=None):
        response = await asyncio.wait_for(self.bus.call(Message(destination=self.destination, path=path,
            interface=iface, member=member, signature=signature, body=body or [])), timeout=8)
        if response.message_type == MessageType.ERROR:
            # D-Bus diagnostics can contain credentials. Never propagate server text.
            raise Refused('service_reseau_indisponible')
        return response.body

    async def props(self, path, iface):
        return unwrap((await self.call(path, 'org.freedesktop.DBus.Properties', 'GetAll', 's', [iface]))[0])

    async def select(self, mac):
        found = []
        for path in (await self.call(ROOT, DEST, 'GetDevices'))[0]:
            d = await self.props(path, DEV)
            if d['DeviceType'] != 2: continue
            w = await self.props(path, WIFI)
            if w.get('PermHwAddress', '').upper() == mac.upper(): found.append((path, d, w))
        if len(found) != 1: raise Refused('cle_wifi_absente_ou_ambigue')
        self.device, d, w = found[0]
        if not re.fullmatch('[A-Za-z0-9_.:-]{1,15}', d['Interface']): raise Refused('interface_invalide')
        self.interface = d['Interface']
        if not d.get('Managed'): raise Refused('interface_non_geree')
        global_state = await self.props(ROOT, DEST)
        if not global_state['WirelessEnabled'] or not global_state['WirelessHardwareEnabled']:
            raise Refused('wifi_desactive')

    async def profiles(self):
        result = []
        for path in (await self.call(SETTINGS, DEST + '.Settings', 'ListConnections'))[0]:
            settings = unwrap((await self.call(path, CONN, 'GetSettings'))[0])
            result.append((path, settings))
        return result

    async def snapshot(self, owned, mac):
        ethernet = False; networks = []; busy = False
        for path in (await self.call(ROOT, DEST, 'GetDevices'))[0]:
            d = await self.props(path, DEV)
            if d['DeviceType'] == 1 and 40 <= d['State'] <= 100: ethernet = True
            if d.get('Ip4Config', '/') != '/':
                addresses = (await self.props(d['Ip4Config'], DEST + '.IP4Config')).get('AddressData', [])
                for address in addresses:
                    if path == self.device and address['address'] == IP: continue
                    networks.append(str(ipaddress.ip_network(f"{address['address']}/{address['prefix']}", strict=False)))
            if path == self.device and d.get('ActiveConnection', '/') != '/':
                a = await self.props(d['ActiveConnection'], ACTIVE)
                busy = a.get('Uuid') not in owned
        foreign = False
        for _, p in await self.profiles():
            c = p.get('connection', {}); w = p.get('802-11-wireless', {})
            if c.get('type') != '802-11-wireless' or c.get('uuid') in owned: continue
            binding = w.get('mac-address')
            if binding and bytes(binding).hex().upper() != mac.replace(':', '').upper(): continue
            if w.get('mode', 'infrastructure') == 'infrastructure': foreign = True
        w = await self.props(self.device, WIFI)
        # WPA2 + AES and AP mode, not merely a USB device being present.
        capable = w['WirelessCapabilities'] & 0x68 == 0x68
        return {'ethernet': ethernet, 'foreign_wifi': foreign, 'ap_capable': capable,
                'networks': networks, 'busy': busy}

    async def scan(self):
        before = (await self.props(self.device, WIFI)).get('LastScan', -1)
        try:
            await self.call(self.device, WIFI, 'RequestScan', 'a{sv}', [{}])
            for _ in range(12):
                await asyncio.sleep(.5)
                if (await self.props(self.device, WIFI)).get('LastScan', -1) > before: break
        except Refused:
            pass  # A single radio may not scan while emitting; manual entry remains available.
        result = {}
        for path in (await self.call(self.device, WIFI, 'GetAllAccessPoints'))[0]:
            ap = await self.props(path, DEST + '.AccessPoint')
            try: ssid = bytes(ap.get('Ssid', [])).decode('utf-8', errors='strict')
            except UnicodeError: continue
            if not ssid or len(ssid.encode()) > 32 or any(ord(c) < 32 for c in ssid): continue
            compatible = bool((ap.get('RsnFlags', 0) | ap.get('WpaFlags', 0)) & 0x100)
            row = {'ssid': ssid, 'strength': int(ap.get('Strength', 0)), 'supported': compatible}
            if ssid not in result or row['strength'] > result[ssid]['strength']: result[ssid] = row
        return sorted(result.values(), key=lambda x: -x['strength'])[:64]

    async def add(self, settings):
        return (await self.call(SETTINGS, DEST + '.Settings', 'AddConnection2', 'a{sa{sv}}ua{sv}', [settings, 2, {}]))[0]

    async def activate(self, path):
        return (await self.call(ROOT, DEST, 'ActivateConnection', 'ooo', [path, self.device, '/']))[0]

    async def checkpoint(self, *, timeout=150, guard=None):
        flags = 0
        if guard:
            # Overlap is allowed only with OUR first-boot expiration checkpoint.
            for cp in (await self.props(ROOT, DEST)).get('Checkpoints', []):
                devices = (await self.props(cp, DEST + '.Checkpoint')).get('Devices', [])
                if self.device in devices and cp != guard:
                    raise Refused('autre_configuration_reseau_en_cours')
            if guard not in (await self.props(ROOT, DEST)).get('Checkpoints', []):
                raise Refused('delai_ecoule')
            if (await self.props(guard, DEST + '.Checkpoint')).get('Devices') != [self.device]:
                raise Refused('point_reprise_inattendu')
            flags = 8
        # Never DESTROY_ALL / DELETE_NEW_CONNECTIONS / global-device flags.
        return (await self.call(ROOT, DEST, 'CheckpointCreate', 'aouu', [[self.device], timeout, flags]))[0]

    async def guard_valid(self, checkpoint):
        return (checkpoint in (await self.props(ROOT, DEST)).get("Checkpoints", [])
                and (await self.props(checkpoint, DEST + ".Checkpoint")).get("Devices") == [self.device])

    async def rollback(self, checkpoint):
        checkpoints = (await self.props(ROOT, DEST)).get('Checkpoints', [])
        if checkpoint not in checkpoints: return  # Host already timed out and rolled back.
        if (await self.props(checkpoint, DEST + '.Checkpoint')).get('Devices') != [self.device]:
            raise Refused('point_reprise_inattendu')
        values = (await self.call(ROOT, DEST, 'CheckpointRollback', 'o', [checkpoint]))[0]
        if any(value != 0 for value in values.values()): raise Refused('retour_reseau_a_verifier')
        # Rollback does not destroy the checkpoint on all supported NM versions.
        if checkpoint in (await self.props(ROOT, DEST)).get('Checkpoints', []):
            await self.call(ROOT, DEST, 'CheckpointDestroy', 'o', [checkpoint])

    async def destroy(self, checkpoint):
        if (await self.props(checkpoint, DEST + '.Checkpoint')).get('Devices') != [self.device]:
            raise Refused('point_reprise_inattendu')
        await self.call(ROOT, DEST, 'CheckpointDestroy', 'o', [checkpoint])

    async def remove(self, identity):
        # Never delete by name, interface, or all Wi-Fi connections.
        for path, p in await self.profiles():
            c = p.get('connection', {})
            if c.get('uuid') == identity and c.get('id') == 'labox-setup-' + identity:
                await self.call(path, CONN, 'Delete')

    async def wait_ip(self, identity, timeout=65):
        for _ in range(timeout):
            d = await self.props(self.device, DEV)
            if d.get('State') == 120:
                reason = d.get('StateReason', [0, 0])[1]
                raise Refused('adresse_ip_non_obtenue' if reason in (15, 16, 17, 18, 19) else 'connexion_wifi_refusee')
            if d.get('State') == 100 and d.get('ActiveConnection', '/') != '/':
                a = await self.props(d['ActiveConnection'], ACTIVE)
                if a.get('Uuid') == identity and d.get('Ip4Config', '/') != '/':
                    p = await self.props(d['Ip4Config'], DEST + '.IP4Config')
                    addresses = p.get('AddressData', [])
                    if addresses:
                        ip = addresses[0]['address']
                        if ip != IP and not ipaddress.ip_address(ip).is_link_local and p.get('Gateway'):
                            return ip
            await asyncio.sleep(1)
        raise Refused('connexion_wifi_non_confirmee')

    async def wait_ap(self, identity):
        for _ in range(30):
            d = await self.props(self.device, DEV)
            if d.get('State') == 100 and d.get('ActiveConnection', '/') != '/':
                a = await self.props(d['ActiveConnection'], ACTIVE)
                if a.get('Uuid') == identity: return
            if d.get('State') == 120: break
            await asyncio.sleep(1)
        raise Refused('point_acces_non_demarre')

    async def persist(self, path, settings):
        settings['connection']['autoconnect'] = Variant('b', True)
        settings['connection']['autoconnect-retries'] = Variant('i', 0)
        settings['ipv6'] = {'method': Variant('s', 'auto')}
        await self.call(path, CONN, 'Update2', 'a{sa{sv}}ua{sv}', [settings, 1, {}])


def portal_reachable(interface):
    """Certificate-checked HTTPS over the candidate Wi-Fi device, never over Ethernet."""
    class BoundHTTPS(http.client.HTTPSConnection):
        def connect(self):
            last = None
            for family, kind, proto, _, address in socket.getaddrinfo(self.host, 443, socket.AF_INET, socket.SOCK_STREAM):
                sock = socket.socket(family, kind, proto); sock.settimeout(5)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b'\0')
                    sock.connect(address)
                    self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                    return
                except OSError as exc:
                    sock.close(); last = exc
            raise last or OSError('unreachable')
    connection = BoundHTTPS('home.123panneaux-solaires.fr', timeout=5)
    try:
        connection.request('GET', '/login', headers={'User-Agent': 'LaBox-Wifi-Setup/0.1', 'Connection': 'close'})
        reply = connection.getresponse(); reply.read(8192)
        return reply.status == 200
    except (OSError, http.client.HTTPException): return False
    finally: connection.close()
