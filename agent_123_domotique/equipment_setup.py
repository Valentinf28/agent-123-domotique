"""Bounded native discovery setup. No generic HA proxy or actuator calls."""
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import time
from pathlib import Path
from shelly_setup import ID, OWNER, ENTITY

ACTION='commissioning.equipment'
DOMAINS={'hue':'Philips Hue','wiz':'WiZ','tplink':'TP-Link Tapo / Kasa','switchbot':'SwitchBot','reolink':'Reolink','enphase_envoy':'Enphase','zha':'Zigbee','matter':'Matter','netatmo':'Netatmo / Legrand','tado':'Tado','home_connect':'Bosch / Siemens','midea':'Midea / SmartHome','homekit_controller':'Appareil HomeKit','shelly':'Shelly','daikin':'Daikin','melcloud':'Mitsubishi Electric / MELCloud','panasonic_cc':'Panasonic Comfort Cloud','smartthings':'Samsung SmartThings','overkiz':'Somfy / Cozytouch / Hi Kumo','gree':'Gree','fronius':'Fronius','nuki':'Nuki','onvif':'ONVIF','ring':'Ring','tuya':'Smart Life / Tuya','huawei_solar':'Huawei Solar','goodwe':'GoodWe','growatt_server':'Growatt','sma':'SMA','solaredge':'SolarEdge','wallbox':'Wallbox / MyWallbox','tesla_wall_connector':'Tesla Wall Connector','openevse':'OpenEVSE','v2c':'V2C Trydan','melcloud_home':'MELCloud Home'}
STEPS={'hue':{'link'},'wiz':{'discovery_confirm'},'tplink':{'discovery_confirm','discovery_auth_confirm','camera_auth_confirm'},'switchbot':{'confirm','password','encrypted_choose_method','encrypted_key','encrypted_auth'},'reolink':{'user'},'enphase_envoy':{'user'}}
SOURCES={'hue':{'zeroconf','homekit'},'wiz':{'dhcp','integration_discovery'},'tplink':{'dhcp','integration_discovery'},'switchbot':{'bluetooth'},'reolink':{'dhcp'},'enphase_envoy':{'zeroconf'}}
UUID=re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
FIELDS={'username','password','token','manual_token','key_id','encryption_key','live_view'}
SECRET_FIELDS={'password','token','key_id','encryption_key'}

def active_entries(call):
 rows=call('/config/config_entries/entry')
 if not isinstance(rows,list):raise RuntimeError('Connexions indisponibles.')
 return [{'entryId':r['entry_id'],'domain':r['domain'],'state':r.get('state','unknown'),'disabled':bool(r.get('disabled_by'))} for r in rows if isinstance(r,dict) and r.get('domain') in DOMAINS and isinstance(r.get('entry_id'),str) and ID.fullmatch(r['entry_id'])]

def discovered(registry,domain):
 rows=registry({'type':'config_entries/flow/progress'})
 if not isinstance(rows,list):raise RuntimeError('Recherche indisponible.')
 out=[]
 for r in rows[:500]:
  c=r.get('context',{}) if isinstance(r,dict) else {};family=r.get('handler') if isinstance(r,dict) else None
  if family!=domain or family not in STEPS or not isinstance(c,dict) or c.get('source') not in SOURCES[family] or r.get('step_id') not in STEPS[family]:continue
  fid=r.get('flow_id');unique=c.get('unique_id');title=c.get('title_placeholders',{})
  if not isinstance(fid,str) or not ID.fullmatch(fid) or not isinstance(unique,str) or not 1<=len(unique)<=160:continue
  fingerprint=hashlib.sha256(json.dumps([family,c['source'],unique,fid],separators=(',',':')).encode()).hexdigest()
  name=title.get('name') or title.get('hostname') or title.get('model') if isinstance(title,dict) else None
  out.append({'flowId':fid,'fingerprint':fingerprint,'name':str(name or DOMAINS[family])[:120],'step':r['step_id']})
 return out[:100]

def device_list(native,call,registry,domain):
 active={e['entryId'] for e in native if e['domain']==domain and not e['disabled'] and e['state']=='loaded'}
 raw=registry({'type':'config/device_registry/list'});entities=registry({'type':'config/entity_registry/list'});areas=registry({'type':'config/area_registry/list'});states=call('/states')
 if not all(isinstance(x,list) for x in (raw,entities,areas,states)):raise RuntimeError('Appareils indisponibles.')
 smap={s.get('entity_id'):s for s in states if isinstance(s,dict)};amap={a.get('area_id'):str(a.get('name',''))[:80] for a in areas if isinstance(a,dict)};out=[]
 allowed=re.compile(r'^(?:switch|light|cover|climate|fan|sensor|binary_sensor|event|camera|lock)\.[a-z0-9_]{1,180}$')
 for d in raw[:3000]:
  if not isinstance(d,dict) or not isinstance(d.get('id'),str) or not ID.fullmatch(d['id']):continue
  refs=[e for e in d.get('config_entries',[]) if e in active]
  if len(refs)!=1:continue
  exposed=[]
  for e in entities[:15000]:
   if not isinstance(e,dict) or e.get('device_id')!=d['id'] or e.get('config_entry_id')!=refs[0] or e.get('platform')!=domain or e.get('disabled_by'):continue
   eid=e.get('entity_id','')
   if not isinstance(eid,str) or not allowed.fullmatch(eid):continue
   s=smap.get(eid,{});a=s.get('attributes',{});a=a if isinstance(a,dict) else {};state=str(s.get('state','unavailable'))[:80]
   exposed.append({'id':eid,'name':str(a.get('friendly_name') or e.get('original_name') or eid)[:120],'domain':eid.split('.')[0],'state':state,'available':state not in ('unknown','unavailable',''),'unit':str(a.get('unit_of_measurement') or '')[:20],'deviceClass':str(a.get('device_class') or e.get('device_class') or e.get('original_device_class') or '')[:40],'reportedAt':str(s.get('last_reported') or s.get('last_updated') or '')[:40]})
  out.append({'id':d['id'],'entryId':refs[0],'domain':domain,'name':str(d.get('name_by_user') or d.get('name') or DOMAINS[domain])[:120],'brand':str(d.get('manufacturer') or DOMAINS[domain])[:120],'model':str(d.get('model') or '')[:120],'room':amap.get(d.get('area_id'),''),'mac':'','entities':exposed[:100]})
 return out[:200]

def form_view(flow,domain):
 if flow.get('type')=='menu' and domain=='switchbot' and flow.get('step_id')=='encrypted_choose_method':return {'kind':'menu','step':flow['step_id'],'fields':[],'choices':['encrypted_key','encrypted_auth'],'retry':False}
 if flow.get('type')!='form' or flow.get('step_id') not in STEPS.get(domain,set()):return {'kind':'blocked','step':str(flow.get('step_id',''))[:40],'fields':[],'choices':[],'retry':False}
 schema=flow.get('data_schema',[]);fields=[]
 if not isinstance(schema,list):raise RuntimeError('Formulaire indisponible.')
 for f in schema:
  name=f.get('name') if isinstance(f,dict) else None
  if name=='host':continue # Never accept an arbitrary target from the portal.
  if name not in FIELDS:return {'kind':'blocked','step':flow['step_id'],'fields':[],'choices':[],'retry':False}
  fields.append({'name':name,'kind':'boolean' if name in ('manual_token','live_view') else 'secret' if name in SECRET_FIELDS else 'text','required':f.get('required') is True})
 return {'kind':'form','step':flow['step_id'],'fields':fields,'choices':[],'retry':bool(flow.get('errors'))}

def local_host(flow):
 for field in flow.get('data_schema',[]):
  if isinstance(field,dict) and field.get('name')=='host':
   options=field.get('options',[]);value=options[0] if len(options)==1 else field.get('default')
   if isinstance(value,(list,tuple)) and len(value)==2:value=value[0]
   try:
    address=ipaddress.IPv4Address(value)
    if any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):return str(address)
   except (ValueError,TypeError):pass
   raise RuntimeError('L’adresse découverte doit être confirmée par la box.')
 return None

def configure(payload,call,*,registry,data=Path('/data'),clock=time.time):
 if isinstance(payload,dict) and str(payload.get('operation','')).startswith('flow_'):
  from integration_flow import configure as configure_flow
  return configure_flow(payload,call,registry=registry,data=data,clock=clock)
 operation=payload.get('operation');domain=payload.get('connector');owner=payload.get('ownerScope','')
 fields={'status':set(),'open':{'session','flowId','fingerprint'},'submit':{'session','flowId','fingerprint','step','values','cloudConsent'},'pair':{'session','operationId','confirmed','code','networkAlreadyConnected'},'close_pairing':{'session'}}
 if operation not in fields or set(payload)!={'operation','connector','ownerScope'}|fields[operation] or domain not in DOMAINS or not isinstance(owner,str) or not OWNER.fullmatch(owner):raise ValueError('Étape de connexion invalide.')
 native=active_entries(call)
 def view():return {'connector':domain,'status':'ready','entries':[e for e in native if e['domain']==domain],'discoveries':discovered(registry,domain),'devices':device_list(native,call,registry,domain),'pairingReady':any(e['domain']==domain and e['state']=='loaded' and not e['disabled'] for e in native)}
 if operation=='status':return view()
 if not isinstance(payload.get('session'),str) or not UUID.fullmatch(payload['session']):raise ValueError('Session invalide.')
 data=Path(data);data.mkdir(exist_ok=True);fd=os.open(data/'equipment-setup.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);file=data/'equipment-setup.json';journal=json.loads(file.read_text()) if file.exists() else {}
  def save():
   tmp=file.with_suffix('.tmp');fd=os.open(tmp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'w') as stream:json.dump(journal,stream)
   tmp.replace(file)
  if operation in ('pair','close_pairing'):
   if domain not in ('zha','matter') or not view()['pairingReady']:raise RuntimeError('La connexion radio doit être configurée sur cette box.')
   key='pair:'+domain;lease=journal.get(key)
   if lease and clock()<lease['expiresAt'] and (lease['ownerScope']!=owner or lease['session']!=payload['session']):raise RuntimeError('Une autre session associe un appareil.')
   if operation=='close_pairing':
    if domain!='zha':raise ValueError('Fermeture indisponible.')
    call('/services/zha/permit',method='POST',payload={'duration':0});journal.pop(key,None);save();return view()
   opid=payload['operationId'];code=payload['code']
   if not isinstance(opid,str) or not UUID.fullmatch(opid) or payload['confirmed'] is not True:raise ValueError('Confirmez l’association.')
   if lease and lease.get('operationId')!=opid and clock()<lease['expiresAt']:raise RuntimeError('Une association reste à vérifier. Actualisez avant de recommencer.')
   if lease and lease.get('operationId')==opid:return {**view(),'notice':'Association déjà envoyée. Actualisez pour retrouver l’appareil.'}
   if domain=='zha' and (code!='' or payload['networkAlreadyConnected'] is not False):raise ValueError('Association Zigbee invalide.')
   if domain=='matter' and (payload['networkAlreadyConnected'] is not True or not isinstance(code,str) or not re.fullmatch(r'(?:\d{11}|\d{21}|MT:[A-Z0-9.\-]{10,120})',code)):raise ValueError('Utilisez le code Matter de partage d’un appareil déjà connecté au réseau.')
   journal[key]={'ownerScope':owner,'session':payload['session'],'operationId':opid,'expiresAt':clock()+(60 if domain=='zha' else 900),'submitted':True};save()
   if domain=='zha':call('/services/zha/permit',method='POST',payload={'duration':60})
   else:registry({'type':'matter/commission','code':code,'network_only':True})
   return {**view(),'notice':'Association ouverte pendant 60 secondes.' if domain=='zha' else 'Association envoyée. Actualisez pour retrouver les fonctions reçues.'}
  fid=payload.get('flowId');candidate=next((d for d in discovered(registry,domain) if d['flowId']==fid and d['fingerprint']==payload.get('fingerprint')),None)
  if not candidate:raise RuntimeError('Cette découverte a changé. Actualisez.')
  flow=call('/config/config_entries/flow/'+fid)
  if not isinstance(flow,dict) or flow.get('flow_id')!=fid or flow.get('handler')!=domain or flow.get('step_id')!=candidate['step']:raise RuntimeError('Le formulaire a changé.')
  current=form_view(flow,domain);lease=journal.get(fid)
  if lease and (lease['ownerScope']!=owner or lease['session']!=payload['session']) and (lease.get('submitted') or clock()<lease['expiresAt']):raise RuntimeError('Une autre session configure cet appareil.')
  if lease and lease.get('submitted'):raise RuntimeError('Un envoi reste à vérifier. Actualisez sans renvoyer les identifiants.')
  if operation=='open':
   journal[fid]={'ownerScope':owner,'session':payload['session'],'fingerprint':candidate['fingerprint'],'expiresAt':clock()+600,'submitted':False};save();return {**view(),'form':{**current,**candidate}}
  if not lease or lease['fingerprint']!=candidate['fingerprint'] or clock()>=lease['expiresAt'] or payload['step']!=flow['step_id'] or current['kind']=='blocked':raise RuntimeError('Cette session ou étape doit être actualisée.')
  values=payload['values']
  if not isinstance(values,dict):raise ValueError('Formulaire invalide.')
  if current['kind']=='menu':
   if set(values)!={'next_step_id'} or values['next_step_id'] not in current['choices']:raise ValueError('Choix invalide.')
  else:
   names={f['name'] for f in current['fields']}
   if not set(values)<=names or any(f['required'] and f['name'] not in values for f in current['fields']):raise ValueError('Formulaire incomplet.')
   for f in current['fields']:
    if f['name'] not in values:continue
    v=values[f['name']]
    if f['kind']=='boolean':
     if type(v) is not bool:raise ValueError('Choix invalide.')
    elif not isinstance(v,str) or len(v)>4096 or f['required'] and not v:raise ValueError('Valeur invalide.')
   host=local_host(flow)
   if host:values={**values,'host':host}
  if domain=='enphase_envoy' and (values.get('username') or values.get('password')) or domain=='switchbot' and (flow['step_id']=='encrypted_auth' or values.get('next_step_id')=='encrypted_auth'):
   if payload['cloudConsent'] is not True:raise ValueError('Autorisez la connexion au compte fabricant.')
  journal[fid]['submitted']=True;save()
  reply=call('/config/config_entries/flow/'+fid,method='POST',payload=values)
  if isinstance(reply,dict) and reply.get('type')=='create_entry':
   native=active_entries(call);created=reply.get('result',{});entry_id=created.get('entry_id') if isinstance(created,dict) else None
   if not any(e['entryId']==entry_id and e['domain']==domain for e in native):raise RuntimeError('La connexion native reste à confirmer.')
   journal.pop(fid,None);save();return {**view(),'notice':'Connexion enregistrée. Actualisez les fonctions de l’appareil.'}
  if isinstance(reply,dict) and reply.get('type') in ('form','menu'):
   journal[fid]['submitted']=False;save();return {**view(),'form':{**form_view(reply,domain),**{k:v for k,v in candidate.items() if k!='step'}}}
  raise RuntimeError('L’envoi reste à vérifier. Actualisez la liste.')
