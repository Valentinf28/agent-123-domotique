"""Read HA's native EV entries/discovery only, without probing arbitrary network targets."""
import re
from lektrico_setup import _devices, OWNER, ID

ACTION = 'commissioning.ev_discover'
# Reviewed core families; unsupported/community routes remain explicit catalogue guidance.
CATALOG = [
    {'domain':'keba','name':'KEBA','connection':'local','adapter':'ha_setup_required'},
    {'domain':'lektrico','name':'Lektrico','connection':'local','adapter':'lektrico'},
    {'domain':'tesla_wall_connector','name':'Tesla Wall Connector','connection':'local','adapter':'ha_setup_required'},
    {'domain':'wallbox','name':'Wallbox','connection':'account_required','adapter':'ha_setup_required'},
    {'domain':'openevse','name':'OpenEVSE','connection':'local','adapter':'ha_setup_required'},
    {'domain':'easee','name':'Easee','connection':'integration_specific','adapter':'unsupported'},
    {'domain':'goe','name':'go-e','connection':'integration_specific','adapter':'unsupported'},
    {'domain':'ocpp','name':'OCPP','connection':'integration_specific','adapter':'unsupported'},
]
READABLE = {row['domain'] for row in CATALOG} | {'goecharger','goecharger_mqtt','goecharger_api2'}


def discover(payload, call, *, registry):
    if not isinstance(payload, dict) or payload.get('operation') != 'status' or not OWNER.fullmatch(str(payload.get('ownerScope', ''))):
        raise ValueError('Recherche non autorisée.')
    if set(payload) != {'operation', 'ownerScope'}:
        raise ValueError('Paramètres inconnus.')
    rows = call('/config/config_entries/entry')
    flows = registry({'type':'config_entries/flow/progress'})
    if not isinstance(rows, list) or not isinstance(flows, list):
        raise RuntimeError('Recherche native indisponible.')
    entries, discoveries, devices = [], [], []
    for family in sorted(READABLE):
        selected = [{'entryId':row['entry_id'],'state':str(row.get('state','unknown'))[:40],'disabled':bool(row.get('disabled_by'))}
                    for row in rows[:500] if isinstance(row, dict) and row.get('domain') == family
                    and isinstance(row.get('entry_id'),str) and ID.fullmatch(row['entry_id'])]
        entries.extend({**row,'domain':family} for row in selected)
        if selected or family == 'keba':
            devices.extend({**device,'domain':family} for device in _devices(selected, call, registry, family))
    for flow in flows[:200]:
        if not isinstance(flow,dict) or flow.get('handler') not in READABLE or not isinstance(flow.get('flow_id'),str) or not ID.fullmatch(flow['flow_id']):
            continue
        context = flow.get('context',{})
        if not isinstance(context,dict) or context.get('source') not in ('zeroconf','ssdp','dhcp','mqtt'):
            continue
        title=context.get('title_placeholders',{})
        title=title if isinstance(title,dict) else {}
        serial=title.get('serial_number','')
        serial=serial if isinstance(serial,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',serial) else ''
        supported=flow['handler']=='lektrico' and flow.get('step_id')=='confirm' and context.get('source')=='zeroconf' and bool(serial)
        discoveries.append({'flowId':flow['flow_id'],'domain':flow['handler'],
            'name':str(title.get('name') or flow['handler'])[:120],'serial':serial,
            'adapter':'lektrico' if supported else 'ha_setup_required'})
    return {'connector':'ev','status':'existing' if entries or devices else 'not_configured','devicesVerified':False,
            'entries':entries[:100],'devices':devices[:100],'discoveries':discoveries[:100],
            'catalog':CATALOG,'search':'native_ha_only'}
