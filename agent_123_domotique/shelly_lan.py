"""Bounded read-only Shelly LAN identification, without Wi-Fi or relay writes."""
import http.client
import ipaddress
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from network_discovery import current_adapters, local_interfaces

_CACHE = (0, [])
_LOCK = threading.Lock()

def identify(host, interfaces, timeout=0.45):
    address = ipaddress.IPv4Address(host)
    if not any(address in interface.network and address not in (
            interface.ip, interface.network.network_address, interface.network.broadcast_address)
            for interface in interfaces):
        raise ValueError('Adresse hors du réseau local de la box.')
    connection = http.client.HTTPConnection(str(address), 80, timeout=timeout)
    try:
        # No proxies, redirects, credentials or arbitrary URLs.
        connection.request('GET', '/shelly', headers={'Accept': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:raise ValueError('Identification indisponible.')
        raw = response.read(4097)
        if len(raw) > 4096:raise ValueError('Réponse trop longue.')
        info = json.loads(raw)
        identity = info.get('mac', '').replace(':', '').replace('-', '').lower()
        if not re.fullmatch('[a-f0-9]{12}', identity) or identity == '000000000000' or int(identity[:2],16) & 1:
            raise ValueError('Identité invalide.')
        # Gen1 exposes a SH... type; Gen2+ an official id/model/gen tuple.
        device_id = info.get('id', '')
        modern = (info.get('gen') in (2,3,4) and isinstance(device_id,str)
                  and re.fullmatch(r'shelly[a-z0-9]+-' + identity, device_id.lower())
                  and isinstance(info.get('model'),str) and 1 <= len(info['model']) <= 80)
        legacy = isinstance(info.get('type'),str) and re.fullmatch(r'SH[A-Z0-9-]{1,30}',info['type'])
        if not (modern or legacy):raise ValueError('Appareil non identifié comme Shelly.')
        return {'flowId':'lan_'+identity, 'domain':'shelly','mac':identity,
                'name':str(info.get('name') or device_id or info['type'])[:120],
                'step':'confirm_discovery','host':str(address)}
    finally:
        connection.close()

def scan(adapters, *, probe=identify, clock=time.monotonic):
    global _CACHE
    interfaces = local_interfaces(current_adapters(adapters))
    key = tuple(str(i) for i in interfaces)
    with _LOCK:
        cached_at, cached = _CACHE
        if getattr(scan, '_network', None) == key and clock()-cached_at < 60:
            return [dict(row) for row in cached]
        # At most 254 addresses, only on directly attached private LANs.
        targets = list(dict.fromkeys(str(ip) for i in interfaces if i.network.num_addresses <= 256
                    for ip in i.network.hosts() if ip != i.ip))[:254]
        def read(host):
            try:return probe(host, interfaces)
            except (OSError,ValueError,TypeError,AttributeError,http.client.HTTPException):return None
        with ThreadPoolExecutor(max_workers=24) as pool:
            rows = [r for r in pool.map(read, targets) if r]
        # An ambiguous MAC is never offered for connection.
        counts = {r['mac']:sum(x['mac']==r['mac'] for x in rows) for r in rows}
        rows = [r for r in rows if counts[r['mac']]==1][:100]
        _CACHE = (clock(), rows);scan._network = key
        return [dict(row) for row in rows]

def start(call, candidate):
    """Create our own native user flow, then submit only its LAN host form."""
    flow = call('/config/config_entries/flow',method='POST',payload={'handler':'shelly','show_advanced_options':False})
    def form(value):
        if (not isinstance(value,dict) or value.get('type')!='form' or value.get('handler')!='shelly'
            or not isinstance(value.get('flow_id'),str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',value['flow_id'])):
            raise RuntimeError('Le formulaire local doit être actualisé.')
        return {f.get('name') for f in value.get('data_schema',[]) if isinstance(f,dict)}
    names=form(flow)
    if flow.get('step_id')=='user' and names=={'device'}:
        # Explicit manual LAN route; never select a BLE device.
        field=flow['data_schema'][0]
        options=field.get('selector',{}).get('select',{}).get('options',[])
        if not any(isinstance(o,dict) and o.get('value')=='manual' for o in options):
            raise RuntimeError('Ajout réseau non proposé par cette version.')
        flow=call('/config/config_entries/flow/'+flow['flow_id'],method='POST',payload={'device':'manual'})
        names=form(flow)
    if flow.get('step_id') not in ('user','user_manual') or 'host' not in names or not names <= {'host','port','verify_ssl'}:
        raise RuntimeError('Le formulaire réseau a changé.')
    values={'host':candidate['host']}
    if 'port' in names:values['port']=80
    if 'verify_ssl' in names:values['verify_ssl']=True
    return flow['flow_id'], values
