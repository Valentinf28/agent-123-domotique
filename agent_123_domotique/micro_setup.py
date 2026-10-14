"""Read-only identity preflight before configuring the pinned AC micro profile."""
import ipaddress
import re
import socket
from network_discovery import local_interfaces, parse_reply
from solar_setup import configure as configure_solar, settings

def configure(payload,adapters,call,**kwargs):
    payload={**payload,'model':'deye_micro'}
    values=settings(payload,adapters)
    mac=payload.get('mac','')
    compact=mac.replace(':','').lower() if isinstance(mac,str) else ''
    if not re.fullmatch('[a-f0-9]{12}',compact) or compact=='000000000000' or int(compact[:2],16)&1:raise ValueError('L’adresse MAC du micro-onduleur est nécessaire.')
    interface=next(i for i in local_interfaces(adapters) if ipaddress.IPv4Address(values['host']) in i.network)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as transport:
        transport.settimeout(3)
        transport.sendto(b'WIFIKIT-214028-READ',(values['host'],48899))
        raw,peer=transport.recvfrom(256)
    found=parse_reply(raw,peer[0],interface)
    if (peer!=(values['host'],48899) or not found or found['loggerSerial']!=values['logger_serial']
            or found['mac'].replace(':','')!=compact):
        raise RuntimeError('L’identité du micro-onduleur ne correspond pas à la recherche.')
    return configure_solar(payload,adapters,call,**kwargs)
