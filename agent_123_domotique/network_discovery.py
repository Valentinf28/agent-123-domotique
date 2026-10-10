"""Bounded, read-only SolarMAN discovery. No login, register writes or pairing.

Wire format documented by davidrapan/ha-solarman (discovery.py, const.py).
Callers supply local interfaces from the operating system, never portal input.
Finding a logger does not prove inverter model, compatibility or integration.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

MESSAGES = (b"WIFIKIT-214028-READ", b"HF-A11ASSISTHREAD")
PRIVATE = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def local_interfaces(adapters):
    interfaces = []
    for adapter in adapters:
        if not isinstance(adapter, dict) or not adapter.get("enabled"):
            continue
        for item in adapter.get("ipv4", []):
            try:
                interface = ipaddress.IPv4Interface(
                    f"{item['address']}/{item['network_prefix']}"
                )
            except (ValueError, KeyError, TypeError):
                continue
            if (any(interface.network.subnet_of(network) for network in PRIVATE)
                    and interface.network.prefixlen <= 30
                    and interface.ip not in (interface.network.network_address,
                                             interface.network.broadcast_address)
                    and interface not in interfaces):
                interfaces.append(interface)
    return interfaces[:8]


def current_adapters(fallback):
    """Read live OS addresses; HA may retain an address from before DHCP renewal."""
    try:
        result = subprocess.run(['ip', '-j', '-4', 'address', 'show', 'up'],
                                capture_output=True, text=True, timeout=3, check=True)
        rows = json.loads(result.stdout)
        adapters = [{'name': row.get('ifname'), 'enabled': True,
                     'ipv4': [{'address': item['local'], 'network_prefix': item['prefixlen']}
                              for item in row.get('addr_info', [])
                              if item.get('family') == 'inet']}
                    for row in rows if isinstance(row, dict)
                    and row.get('ifname') != 'lo'
                    and not row.get('ifname', '').startswith(('docker', 'veth', 'hassio', 'br-'))]
        if local_interfaces(adapters):
            return adapters
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        pass
    return fallback


def parse_reply(data, sender, interface):
    if len(data) > 256:
        return None
    try:
        address, mac, serial = data.decode("ascii").strip().split(",")
        ip = ipaddress.IPv4Address(address)
        serial_number = int(serial) if re.fullmatch(r"[0-9]{1,10}", serial) else 0
        compact_mac = mac.replace(":", "").replace("-", "").lower()
        if (address != sender or ip not in interface.network or ip == interface.ip
                or ip in (interface.network.network_address, interface.network.broadcast_address)
                or not 0 < serial_number <= 0xffffffff
                or not re.fullmatch(r"[0-9a-f]{12}", compact_mac)
                or compact_mac == "000000000000" or int(compact_mac[:2], 16) & 1):
            return None
    except (ValueError, UnicodeError):
        return None
    normalized_mac = ":".join(compact_mac[i:i+2] for i in range(0, 12, 2))
    return {
        "id": f"solarman:{normalized_mac}:{serial_number}",
        "connector": "solarman", "label": "Boîtier solaire SolarMAN",
        "host": address, "mac": normalized_mac, "loggerSerial": serial_number,
        "status": "found", "integrated": False,
    }


def discover_solarman(adapters, duration=2.0):
    interfaces = local_interfaces(current_adapters(adapters))
    if not interfaces:
        raise RuntimeError("Aucun réseau local utilisable pour la recherche.")
    # One bounded window per interface, at most 8 interfaces / 16 seconds.
    duration = min(2.0, max(0.1, float(duration)))
    found = {}
    errors = []
    for interface in interfaces:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transport:
                transport.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                transport.bind((str(interface.ip), 0))
                for message in MESSAGES:
                    transport.sendto(message, (str(interface.network.broadcast_address), 48899))
                deadline = time.monotonic() + duration
                packets = 0
                while packets < 512 and time.monotonic() < deadline:
                    transport.settimeout(max(0.001, deadline - time.monotonic()))
                    try:
                        data, sender = transport.recvfrom(257)
                    except socket.timeout:
                        break
                    packets += 1
                    device = parse_reply(data, sender[0], interface)
                    if device:
                        previous = found.get(device["id"])
                        if previous and previous["host"] != device["host"]:
                            previous["status"] = "ambiguous"
                        else:
                            found[device["id"]] = device
        except OSError:
            errors.append("La recherche n’a pas pu accéder à un réseau local de la box.")
    if len(errors) == len(interfaces):
        raise RuntimeError("La box ne peut pas rechercher les appareils sur son réseau local.")
    # Some loggers disable UDP discovery but keep their local data port open.
    # An open port is only a candidate, never sufficient to assign a brand.
    for interface in interfaces:
        if interface.network.num_addresses > 256:
            errors.append("Recherche complémentaire limitée aux réseaux de 256 adresses maximum.")
            continue
        known = {device["host"] for device in found.values()}
        hosts = [str(ip) for ip in interface.network.hosts()
                 if ip != interface.ip and str(ip) not in known]
        def probe(host):
            try:
                with socket.create_connection((host, 8899), timeout=0.2,
                                              source_address=(str(interface.ip), 0)):
                    return host
            except OSError:
                return None
        with ThreadPoolExecutor(max_workers=16) as pool:
            for host in pool.map(probe, hosts):
                if host:
                    found[f"tcp8899:{host}"] = {
                        "id": f"tcp8899:{host}", "label": "Appareil à identifier",
                        "host": host, "port": 8899, "status": "unidentified",
                        "integrated": False,
                    }
    return {"devices": sorted(found.values(), key=lambda item: item["id"]),
            "warnings": errors, "protocols": ["solarman"],
            "scope": "solar_loggers", "completedAt": time.time()}
