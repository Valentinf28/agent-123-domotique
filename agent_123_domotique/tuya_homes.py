"""Read Tuya home membership locally; HA remains the sole credential writer.

Only the native Tuya entry's current credentials are used in memory. No token
refresh, config writes, device controls, SDK MQTT client or cloud logs.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

SAFE = re.compile(r'^[A-Za-z0-9_-]{1,100}$')

def _api(data):
    from tuya_sharing.customerapi import CustomerApi, CustomerTokenInfo
    from tuya_sharing.customerlogging import logger
    logger.disabled = True
    endpoint = data.get('endpoint', '')
    parsed = urlsplit(endpoint)
    # Native integration supplied endpoint, never a browser-supplied URL.
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or parsed.path not in ('', '/') or parsed.query or parsed.fragment or not re.fullmatch(r'apigw(?:-[a-z]+)?\.(?:iotbing\.com|tuya(?:eu|us|cn|in)?\.com)', parsed.hostname or ''):
        raise ValueError('Endpoint unavailable')
    token = data.get('token_info')
    if not isinstance(token, dict) or not all(isinstance(token.get(k), str) and token[k] for k in ('access_token', 'refresh_token')):
        raise ValueError('Native credentials unavailable')
    class ReadOnlyApi(CustomerApi):
        def refresh_access_token_if_need(self):
            if self.token_info.expire_time - 30000 <= int(time.time() * 1000):
                raise ValueError('Native credentials must be refreshed by HA')
    api = ReadOnlyApi(CustomerTokenInfo(token), 'HA_3y9q4ak7g4ephrvke', data['user_code'], endpoint.rstrip('/'), None)
    original = api.session.request
    def request(method, url, **kwargs):
        if method != 'GET' or url not in (endpoint.rstrip('/')+'/v1.0/m/life/users/homes', endpoint.rstrip('/')+'/v1.0/m/life/ha/home/devices'):
            raise ValueError('Read-only home inventory')
        return original(method, url, **kwargs, timeout=4, allow_redirects=False)
    api.session.request = request
    return api

def read_homes(entries, *, config=Path('/homeassistant_config'), api_factory=_api, now=time.monotonic):
    """Return only entry/home names and membership; never return SDK objects."""
    storage = Path(config)/'.storage/core.config_entries'
    if storage.is_symlink() or storage.stat().st_size > 16_000_000:
        raise ValueError('Native configuration unavailable')
    raw = json.loads(storage.read_text())
    native = {e['entry_id']:e for e in raw['data']['entries'] if isinstance(e, dict) and e.get('domain') == 'tuya'}
    homes, membership = [], {}
    deadline = now()+18
    for entry in entries:
        if entry['disabled'] or entry['state'] != 'loaded':
            continue
        entry_id = entry['entryId']
        current = native.get(entry_id)
        if not current:
            raise ValueError('Native connection changed')
        api = api_factory(current['data'])
        try:
            response = api.get('/v1.0/m/life/users/homes')
            if not isinstance(response, dict) or response.get('success') is not True or not isinstance(response.get('result'), list) or len(response['result']) > 20:
                raise ValueError('Homes unavailable')
            for home in response['result']:
                if now() >= deadline:
                    raise TimeoutError('Home inventory deadline')
                home_id = str(home['ownerId'])
                if not SAFE.fullmatch(home_id) or not isinstance(home.get('name'), str) or not home['name'].strip():
                    raise ValueError('Home unavailable')
                key = entry_id+':'+home_id
                if any(h['id'] == key for h in homes):
                    raise ValueError('Ambiguous home')
                devices = api.get('/v1.0/m/life/ha/home/devices', {'homeId':home_id})
                if not isinstance(devices, dict) or devices.get('success') is not True or not isinstance(devices.get('result'), list):
                    raise ValueError('Membership unavailable')
                homes.append({'id':key, 'name':home['name'].strip()[:120]})
                for device in devices['result']:
                    device_id = device.get('id') if isinstance(device, dict) else None
                    if not isinstance(device_id, str) or not SAFE.fullmatch(device_id):
                        raise ValueError('Membership unavailable')
                    membership.setdefault((entry_id, device_id), []).append(key)
        finally:
            api.session.close()
    return homes, membership
