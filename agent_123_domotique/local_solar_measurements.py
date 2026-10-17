"""Read-only, entry/model-scoped evidence for AC micro production and mono meter."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from connector_install import MANAGED_VERSION as SOLARMAN_VERSION
from solar_profile import MICRO_PROFILE, MICRO_PROFILE_SHA
from ddzy422_setup import DOMAIN, verify_bundle

MODELS={'deye_micro':'solarman','ddzy422':DOMAIN}
ROLE_NAMES={'production':'Power'}
DDZY_KEYS={'gridPower':'gridPowerW','importEnergy':'importTotalKwh','exportEnergy':'exportTotalKwh'}

def readiness(call,manifest):
    handlers=call('/config/config_entries/flow_handlers')
    if not isinstance(handlers,list):raise RuntimeError('La liste des connecteurs est indisponible.')
    def ready(domain,version):
        try:value=manifest(domain)
        except Exception:return False
        return domain in handlers and isinstance(value,dict) and value.get('domain')==domain and value.get('version')==version and value.get('is_built_in') is False
    return {'solarmanReady':ready('solarman',SOLARMAN_VERSION),'ddzyReady':ready(DOMAIN,verify_bundle()['version'])}

def inspect(entry_id,model,call,registry,*,config=Path('/homeassistant_config'),now=None):
    if model not in MODELS or not isinstance(entry_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',entry_id):
        raise ValueError('Connexion ou modèle solaire invalide.')
    if not isinstance(registry,list):raise RuntimeError('Le registre des mesures est indisponible.')
    config=Path(config);domain=MODELS[model]
    stored=json.loads((config/'.storage/core.config_entries').read_text())['data']['entries']
    matches=[e for e in stored if e.get('entry_id')==entry_id and e.get('domain')==domain]
    if len(matches)!=1:raise RuntimeError('La connexion demandée ne correspond pas à ce modèle.')
    entry=matches[0]
    if entry.get('disabled_by'):raise RuntimeError('Cette connexion est désactivée.')
    if model=='deye_micro':
        profile=config/'custom_components/solarman/inverter_definitions/custom'/MICRO_PROFILE
        options=entry.get('options',{})
        if (options.get('lookup_file')!='custom/'+MICRO_PROFILE or profile.is_symlink()
                or not profile.is_file() or hashlib.sha256(profile.read_bytes()).hexdigest()!=MICRO_PROFILE_SHA):
            raise RuntimeError('La connexion ne possède pas le profil AC micro-onduleur vérifié.')
        serial=options.get('logger_serial')
    else:
        target=config/'custom_components'/DOMAIN
        for name,checksum in verify_bundle()['files'].items():
            path=target/name
            if target.is_symlink() or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
                raise RuntimeError('Le lecteur natif du compteur ne correspond pas au paquet vérifié.')
        serial=entry.get('data',{}).get('logger_serial')
    if type(serial) is not int or not 0<serial<=0xffffffff:raise RuntimeError('L’identité de cette connexion est incomplète.')
    live=call('/config/config_entries/entry?domain='+domain)
    if not isinstance(live,list):raise RuntimeError('La connexion active ne peut pas être vérifiée.')
    active=[e for e in live if e.get('entry_id')==entry_id]
    roles=['production'] if model=='deye_micro' else list(DDZY_KEYS)
    result={'entryId':entry_id,'model':model,'connector':domain,'readingsAvailable':False,'entities':{},
            'measurements':{role:{'status':'missing'} for role in roles},'physicalTestVerified':False}
    if len(active)!=1 or active[0].get('state')!='loaded' or active[0].get('disabled_by'):return result
    rows=[e for e in registry if e.get('config_entry_id')==entry_id and e.get('platform')==domain
          and not e.get('disabled_by') and isinstance(e.get('entity_id'),str)
          and re.fullmatch(r'sensor\.[a-z0-9_]+',e['entity_id'])]
    for role in roles:
        selected=[e for e in rows if (e.get('original_name')==ROLE_NAMES[role] if model=='deye_micro'
                  else e.get('unique_id')==f'{DOMAIN}_{serial}_{DDZY_KEYS[role]}')]
        if len(selected)>1:raise RuntimeError('Les mesures de cette connexion sont ambiguës.')
        if selected:result['entities'][role]=selected[0]['entity_id']
    ids=sorted(set(result['entities'].values()))
    if len(ids)>8:raise RuntimeError('Le registre de cette connexion est ambigu.')
    template=("{% set ns = namespace(rows=[]) %}{% for id in "+json.dumps(ids)+" %}"
        "{% set s = states[id] %}{% if s is defined and s is not none %}"
        "{% set ns.rows = ns.rows + [dict(entity_id=id, state=s.state, attributes=dict(s.attributes), last_reported=s.last_reported.isoformat())] %}"
        "{% endif %}{% endfor %}{{ ns.rows | to_json }}")
    states=call('/template',method='POST',payload={'template':template})
    if not isinstance(states,list):raise RuntimeError('Les mesures actuelles de cette connexion sont indisponibles.')
    now=now or datetime.now(timezone.utc)
    for role,entity_id in result['entities'].items():
        readings=[s for s in states if s.get('entity_id')==entity_id]
        if len(readings)!=1:continue
        row=readings[0]
        try:
            value=float(row.get('state'));attrs=row.get('attributes',{})
            reported=datetime.fromisoformat(row.get('last_reported','').replace('Z','+00:00'))
            if reported.tzinfo is None or not math.isfinite(value):raise ValueError()
            energy=role in ('importEnergy','exportEnergy')
            if energy:
                if attrs.get('unit_of_measurement') not in ('Wh','kWh') or attrs.get('device_class')!='energy' or attrs.get('state_class')!='total_increasing' or value<0:raise ValueError()
                if attrs['unit_of_measurement']=='Wh':value/=1000
                unit='kWh'
            else:
                if attrs.get('unit_of_measurement') not in ('W','kW') or attrs.get('device_class')!='power':raise ValueError()
                if attrs['unit_of_measurement']=='kW':value*=1000
                if abs(value)>25000 or (role=='production' and not 0<=value<=4000):raise ValueError()
                unit='W'
            age=(now-reported).total_seconds()
            result['measurements'][role]={'status':'recent' if -5<=age<=90 else 'stale','value':value,'unit':unit,'reportedAt':reported.isoformat()}
        except (ValueError,TypeError,OverflowError):result['measurements'][role]={'status':'unavailable'}
    result['readingsAvailable']=all(m['status']=='recent' for m in result['measurements'].values())
    return result
