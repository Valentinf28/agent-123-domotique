"""Local Shelly and Shelly BLU onboarding through native HA discovery and verified local LAN identification.

Never operates a relay, configures Wi-Fi, refreshes cloud credentials or persists
passwords / BLE keys. Discovery flow identities are rechecked on every write.
"""
import fcntl
import json
import os
import re
import time
from pathlib import Path

ACTION = 'commissioning.shelly'
ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
UUID = re.compile(r'^[a-f0-9-]{36}$')
OWNER = re.compile(r'^[a-f0-9]{64}$')
DOMAINS = {'shelly':('zeroconf', {'confirm_discovery','credentials'}), 'bthome':('bluetooth', {'bluetooth_confirm','get_encryption_key'})}
ENTITY = re.compile(r'^(?:switch|light|cover|climate|fan|sensor|binary_sensor|event|button|number|select)\.[a-z0-9_]{1,180}$')

def mac(value):
    if not isinstance(value,str):return None
    clean = re.sub(r'[:-]', '', value).lower()
    return clean if re.fullmatch('[a-f0-9]{12}',clean) else None

def blu_name(name):
    # Native Shelly names for BLU Door/Window, Button, Motion, H&T and Wall Switch.
    return isinstance(name,str) and bool(re.match(r'^(?:Shelly(?:\s|[ _-])*BLU\b|SB(?:DW|BT|MO|HT|WS|RC)[-_])',name,re.I))

def entries(call):
    rows=call('/config/config_entries/entry')
    if not isinstance(rows,list):raise RuntimeError('Connexions locales indisponibles.')
    return [{'entryId':r['entry_id'],'domain':r['domain'],'state':str(r.get('state','unknown'))[:40],'disabled':bool(r.get('disabled_by'))}
      for r in rows if isinstance(r,dict) and r.get('domain') in (*DOMAINS,'bluetooth') and isinstance(r.get('entry_id'),str) and ID.fullmatch(r['entry_id'])]

def discoveries(registry):
    rows=registry({'type':'config_entries/flow/progress'})
    if not isinstance(rows,list):raise RuntimeError('Recherche locale indisponible.')
    found=[]
    for row in rows[:500]:
        if not isinstance(row,dict) or row.get('handler') not in DOMAINS:continue
        domain=row['handler'];context=row.get('context',{});source,steps=DOMAINS[domain]
        if not isinstance(context,dict) or context.get('source')!=source or row.get('step_id') not in steps:continue
        title=context.get('title_placeholders',{});name=title.get('name') if isinstance(title,dict) else None
        identity=mac(context.get('unique_id'));flow_id=row.get('flow_id')
        if not identity or not isinstance(flow_id,str) or not ID.fullmatch(flow_id) or domain=='bthome' and not blu_name(name):continue
        found.append({'flowId':flow_id,'domain':domain,'mac':identity,'name':str(name or 'Shelly '+identity[-6:])[:120],'step':row['step_id']})
    return found[:100]

def devices(native,call,registry):
    active={e['entryId']:e['domain'] for e in native if not e['disabled'] and e['domain'] in DOMAINS}
    raw_devices=registry({'type':'config/device_registry/list'});entities=registry({'type':'config/entity_registry/list'});areas=registry({'type':'config/area_registry/list'});states=call('/states')
    if not all(isinstance(rows,list) for rows in (raw_devices,entities,areas,states)):raise RuntimeError('Appareils locaux indisponibles.')
    area_map={r.get('area_id'):str(r.get('name',''))[:80] for r in areas if isinstance(r,dict)}
    state_map={r.get('entity_id'):r for r in states if isinstance(r,dict)}
    result=[]
    for device in raw_devices[:3000]:
        if not isinstance(device,dict) or not isinstance(device.get('id'),str) or not ID.fullmatch(device['id']):continue
        refs=[e for e in device.get('config_entries',[]) if e in active]
        if len(refs)!=1:continue
        domain=active[refs[0]];manufacturer=str(device.get('manufacturer',''));model=str(device.get('model',''));name=str(device.get('name_by_user') or device.get('name') or 'Shelly')
        if domain=='bthome' and not (manufacturer.lower() in ('shelly','allterco robotics') or blu_name(model) or blu_name(str(device.get('name','')))):continue
        identities={mac(pair[1]) for pair in device.get('connections',[]) if isinstance(pair,(tuple,list)) and len(pair)==2 and pair[0] in ('mac','bluetooth')}
        identities|={mac(pair[1]) for pair in device.get('identifiers',[]) if isinstance(pair,(tuple,list)) and len(pair)==2 and pair[0] in DOMAINS}
        identities.discard(None)
        exposed=[]
        for entity in entities[:15000]:
            if not isinstance(entity,dict) or entity.get('device_id')!=device['id'] or entity.get('config_entry_id')!=refs[0] or entity.get('platform')!=domain or entity.get('disabled_by'):continue
            entity_id=entity.get('entity_id','')
            if not isinstance(entity_id,str) or not ENTITY.fullmatch(entity_id):continue
            raw=state_map.get(entity_id,{});attrs=raw.get('attributes',{});attrs=attrs if isinstance(attrs,dict) else {};state=str(raw.get('state','unavailable'))[:80]
            exposed.append({'id':entity_id,'name':str(attrs.get('friendly_name') or entity.get('original_name') or entity_id)[:120], 'domain':entity_id.split('.')[0],'state':state,'available':state.lower() not in ('unknown','unavailable',''), 'unit':str(attrs.get('unit_of_measurement') or '')[:20], 'deviceClass':str(attrs.get('device_class') or entity.get('device_class') or entity.get('original_device_class') or '')[:40], 'reportedAt':str(raw.get('last_reported') or raw.get('last_updated') or '')[:40]})
        result.append({'id':device['id'],'entryId':refs[0],'domain':domain,'mac':next(iter(identities)) if len(identities)==1 else '', 'name':name[:120],'brand':'Shelly','model':model[:120],'room':area_map.get(device.get('area_id'),''),'entities':exposed[:100]})
    return result[:200]

def configure(payload,call,*,registry,data=Path('/data'),clock=time.time,lan=None,identify=None):
    operation=payload.get('operation');owner=payload.get('ownerScope','')
    fields={'status':set(),'connect':{'session','flowId','mac','confirmed'},'credentials':{'session','flowId','mac','username','password'},'key':{'session','flowId','mac','bindkey'}}
    if operation not in fields or set(payload)!={'operation','ownerScope'}|fields[operation] or not isinstance(owner,str) or not OWNER.fullmatch(owner):raise ValueError('Étape locale invalide.')
    native=entries(call)
    journal={}
    file=Path(data)/'shelly-setup.json'
    if file.exists():journal=json.loads(file.read_text())
    def found():
        rows=discoveries(registry)
        connected={d['mac'] for d in devices(native,call,registry)}
        for candidate in lan() if lan else []:
            if candidate['mac'] in connected or any(d['mac']==candidate['mac'] for d in rows):continue
            row={k:candidate[k] for k in ('flowId','domain','mac','name','step')}
            lease=journal.get(row['flowId'],{})
            if lease.get('ownerScope')==owner and lease.get('nativeFlowId') and lease.get('step')=='credentials':row['step']='credentials'
            rows.append(row)
        return rows[:100]
    def view():return {'connector':'shelly','status':'ready','devicesVerified':False,'entries':[e for e in native if e['domain'] in DOMAINS],'bluetoothConfigured':any(e['domain']=='bluetooth' and e['state']=='loaded' and not e['disabled'] for e in native),'discoveries':found(),'devices':devices(native,call,registry)}
    if operation=='status':return view()
    session=payload['session'];flow_id=payload['flowId'];identity=mac(payload['mac'])
    if not isinstance(session,str) or not UUID.fullmatch(session) or not isinstance(flow_id,str) or not ID.fullmatch(flow_id) or not identity:raise ValueError('Choisissez un appareil découvert par cette box.')
    if operation=='connect' and payload['confirmed'] is not True:raise ValueError('Confirmez cet appareil.')
    data=Path(data);data.mkdir(exist_ok=True);fd=os.open(data/'shelly-setup.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);file=data/'shelly-setup.json';journal=json.loads(file.read_text()) if file.exists() else {}
        def save():
            temporary=file.with_suffix('.tmp');fd=os.open(temporary,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(journal,stream)
            temporary.replace(file)
        # A lost reply must be reconciled by native identity, never reposted.
        connected=[d for d in devices(native,call,registry) if d['mac']==identity]
        if connected:return view()
        candidate=next((d for d in found() if d['flowId']==flow_id and d['mac']==identity),None)
        if not candidate:raise RuntimeError('Cette découverte a changé. Actualisez la recherche.')
        lease=journal.get(flow_id)
        if lease and (lease['ownerScope']!=owner or lease['session']!=session):
            if lease.get('submitted') or clock()<lease['expiresAt']:raise RuntimeError('Une autre session configure cet appareil.')
            lease=None
        if lease and lease.get('submitted'):raise RuntimeError('La box vérifie encore le dernier envoi. Actualisez sans renvoyer les identifiants.')
        if lease and clock()>=lease['expiresAt']:
            if operation=='connect' and not lease.get('submitted'):lease=None
            else:raise RuntimeError('Cette session locale a expiré. Actualisez la recherche.')
        lan_candidate=None
        native_flow_id=lease.get('nativeFlowId',flow_id) if lease else flow_id
        if flow_id.startswith('lan_'):
            lan_candidate=next((d for d in lan() if d['flowId']==flow_id and d['mac']==identity),None) if lan else None
            if not lan_candidate or not identify or identify(lan_candidate['host'])['mac']!=identity:
                raise RuntimeError('L’identité réseau de cet appareil a changé. Actualisez.')
            if not lease or not lease.get('nativeFlowId'):
                if operation!='connect':raise RuntimeError('Reprenez la connexion de cet appareil.')
                journal[flow_id]={**(journal.get(flow_id) or {}),'ownerScope':owner,'session':session,'mac':identity,'expiresAt':clock()+600,'submitted':True};save()
                from shelly_lan import start
                native_flow_id,values=start(call,lan_candidate)
                # Recheck DHCP identity immediately before the native host submission.
                if identify(lan_candidate['host'])['mac']!=identity:raise RuntimeError('L’appareil a changé d’adresse.')
                journal[flow_id]['nativeFlowId']=native_flow_id;save()
                flow=call('/config/config_entries/flow/'+native_flow_id,method='POST',payload=values)
                if isinstance(flow,dict) and flow.get('type')=='create_entry':
                    created=flow.get('result',{})
                    if mac(created.get('unique_id'))!=identity:raise RuntimeError('Identité native non confirmée.')
                    native=entries(call)
                    if not any(e['entryId']==created.get('entry_id') and e['domain']=='shelly' for e in native):raise RuntimeError('Connexion native à actualiser.')
                    journal.pop(flow_id,None);save();return view()
                if not isinstance(flow,dict) or flow.get('type')!='form' or flow.get('step_id')!='credentials':
                    raise RuntimeError('La connexion réseau n’a pas été confirmée.')
                journal[flow_id].update(submitted=False,step='credentials');save();lease=journal[flow_id]
                candidate['step']='credentials'
            else:flow=call('/config/config_entries/flow/'+native_flow_id)
        else:flow=call('/config/config_entries/flow/'+native_flow_id)
        if not isinstance(flow,dict) or flow.get('flow_id')!=native_flow_id or flow.get('handler')!=candidate['domain'] or flow.get('type')!='form' or flow.get('step_id')!=candidate['step']:
            raise RuntimeError('Le formulaire local a changé. Actualisez la recherche.')
        schema=flow.get('data_schema',[]);names={f.get('name') for f in schema if isinstance(f,dict)}
        if operation=='connect' and candidate['step'] in ('credentials','get_encryption_key'):
            journal[flow_id]={**(journal.get(flow_id) or {}),'ownerScope':owner,'session':session,'mac':identity,'expiresAt':clock()+600,'submitted':False};save()
            return {**view(),'authentication':{'flowId':flow_id,'mac':identity,'name':candidate['name'],'kind':'key' if candidate['step']=='get_encryption_key' else 'password','usernameRequired':'username' in names}}
        values={}
        if operation=='credentials':
            if not lease or candidate['step']!='credentials' or not names<= {'username','password'} or 'password' not in names or not isinstance(payload['password'],str) or not 1<=len(payload['password'])<=128 or not isinstance(payload['username'],str) or len(payload['username'])>80:raise ValueError('Renseignez le mot de passe local de ce Shelly.')
            values={'password':payload['password']}
            if 'username' in names:
                if not payload['username']:raise ValueError('Renseignez le nom d’utilisateur local.')
                values['username']=payload['username']
        elif operation=='key':
            if not lease or candidate['step']!='get_encryption_key' or names!={'bindkey'} or not isinstance(payload['bindkey'],str) or not re.fullmatch('[a-fA-F0-9]{32}',payload['bindkey']):raise ValueError('Recopiez la clé Bluetooth de 32 caractères de ce capteur.')
            values={'bindkey':payload['bindkey']}
        elif candidate['step'] not in ('confirm_discovery','bluetooth_confirm'):raise RuntimeError('Cette étape nécessite une autre vérification.')
        journal[flow_id]={**(journal.get(flow_id) or {}),'ownerScope':owner,'session':session,'mac':identity,'expiresAt':clock()+600,'submitted':True};save()
        # No exception strings or native response data are returned to the caller.
        reply=call('/config/config_entries/flow/'+native_flow_id,method='POST',payload=values)
        if isinstance(reply,dict) and reply.get('type')=='create_entry':
            native=entries(call);created=reply.get('result',{});
            if lan_candidate and mac(created.get('unique_id'))!=identity:raise RuntimeError('Identité native non confirmée.')
            entry_id=created.get('entry_id') if isinstance(created,dict) else None
            if not any(e['entryId']==entry_id and e['domain']==candidate['domain'] for e in native):raise RuntimeError('La connexion native n’a pas encore été confirmée. Actualisez la recherche.')
            journal.pop(flow_id,None);save();return view()
        if isinstance(reply,dict) and reply.get('type')=='form' and reply.get('step_id') in ('credentials','get_encryption_key'):
            journal[flow_id]['submitted']=False;save()
            return {**view(),'authentication':{'flowId':flow_id,'mac':identity,'name':candidate['name'],'kind':'key' if reply['step_id']=='get_encryption_key' else 'password','usernameRequired':any(f.get('name')=='username' for f in reply.get('data_schema',[]) if isinstance(f,dict)),'retry':bool(reply.get('errors'))}}
        raise RuntimeError('La connexion n’a pas été confirmée. Actualisez la liste.')
