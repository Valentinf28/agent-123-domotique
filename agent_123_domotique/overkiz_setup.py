"""Native Somfy Overkiz setup, direct sessions only; never a cover command."""
import fcntl
import json
import os
from pathlib import Path
import re
import time
import urllib.error

OWNER=re.compile(r'^[a-f0-9]{64}$')
SESSION=re.compile(r'^[a-f0-9-]{36}$')
ID=re.compile(r'^[A-Za-z0-9_-]{1,100}$')
TTL=600
# Native pyoverkiz Server values, verified against upstream enums/server.py.
SOMFY={'somfy_europe','somfy_america','somfy_oceania','somfy_developer_mode'}
FIELDS={'status':set(),'start':{'session'},'hub':{'session','hub'},'mode':{'session','mode'},'credentials':{'session','username','password','cloudConsent'},'local':{'session','host','token','verifySsl'},'cancel':{'session'}}
SCHEMAS={'user':{'hub'},'local_or_cloud':{'api_type'},'cloud':{'username','password'},'local':{'host','token','verify_ssl'}}

def valid_local_host(host):
    # Restrict to the native gateway PIN hostname. No URLs, userinfo or arbitrary LAN targets.
    return isinstance(host,str) and bool(re.fullmatch(r'gateway-[0-9]{4}-[0-9]{4}-[0-9]{4}\.local(?::8443)?',host))

def _entries(call):
    rows=call('/config/config_entries/entry?domain=overkiz')
    if not isinstance(rows,list):raise RuntimeError('Connexions indisponibles.')
    return [{'entryId':r['entry_id'],'state':str(r.get('state','unknown'))[:40],'disabled':bool(r.get('disabled_by'))} for r in rows if isinstance(r,dict) and r.get('domain')=='overkiz' and isinstance(r.get('entry_id'),str) and ID.fullmatch(r['entry_id'])]

def _choices(flow,field):
    schema=flow.get('data_schema');row=next((r for r in schema if r.get('name')==field),{})
    options=row.get('options') or row.get('selector',{}).get('select',{}).get('options',[])
    if isinstance(options,dict):options=list(options.items())
    if not isinstance(options,list):return []
    choices=[]
    for option in options[:100]:
        if isinstance(option,(list,tuple)) and len(option)==2:value,label=option
        elif isinstance(option,dict):value,label=option.get('value'),option.get('label',option.get('value'))
        elif isinstance(option,str):value,label=option,option
        else:continue
        if not isinstance(value,str) or not isinstance(label,str):continue
        if field=='hub' and value not in SOMFY:continue
        if field=='api_type' and value not in ('local','cloud'):continue
        choices.append({'id':value,'name':label[:120]})
    return choices

def _form(flow):
    if not isinstance(flow,dict) or flow.get('handler') not in (None,'overkiz'):raise RuntimeError('Formulaire non reconnu.')
    if flow.get('type')=='abort':return {'status':'aborted','choices':[],'retry':False}
    step=flow.get('step_id');schema=flow.get('data_schema')
    if flow.get('type')!='form' or step not in SCHEMAS or not isinstance(schema,list) or any(not isinstance(r,dict) or not isinstance(r.get('name'),str) for r in schema) or len(schema)!=len(SCHEMAS[step]) or {r['name'] for r in schema}!=SCHEMAS[step]:raise RuntimeError('Version du formulaire non reconnue.')
    choices=_choices(flow,'hub' if step=='user' else 'api_type') if step in ('user','local_or_cloud') else []
    if step in ('user','local_or_cloud') and not choices:raise RuntimeError('Aucun choix Somfy compatible.')
    return {'status':{'user':'hub','local_or_cloud':'mode','cloud':'credentials','local':'local'}[step],'choices':choices,'retry':bool(flow.get('errors'))}

def configure(payload,call,*,data=Path('/data'),now=None):
    base={'connector':'overkiz','status':'needs_help','choices':[],'entries':[],'retry':False,'devicesVerified':False}
    if not isinstance(payload,dict) or not isinstance(payload.get('ownerScope'),str) or not OWNER.fullmatch(payload['ownerScope']):raise ValueError('Propriétaire non vérifié.')
    operation=payload.get('operation');session=payload.get('session');owner=payload['ownerScope']
    if operation not in FIELDS or set(payload)!={'operation','ownerScope'}|FIELDS[operation]:raise ValueError('Étape Somfy inconnue.')
    if operation!='status' and (not isinstance(session,str) or not SESSION.fullmatch(session)):raise ValueError('Session non vérifiée.')
    try:return _configure(payload,call,base,data,time.time() if now is None else now)
    except Exception:
        # HA exception strings and form defaults may contain account/token/host details.
        return base

def _configure(payload,call,base,data,now):
    operation=payload['operation'];owner=payload['ownerScope'];session=payload.get('session')
    entries=_entries(call);base={**base,'entries':entries}
    if operation=='status':return {**base,'status':'existing' if entries else 'not_configured'}
    data=Path(data);data.mkdir(exist_ok=True);fd=os.open(data/'overkiz-flow.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);os.fchmod(lock.fileno(),0o600);journal=data/'overkiz-flow.json'
        if journal.exists():
            descriptor=os.open(journal,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(descriptor) as stream:state=json.load(stream)
        else:state={}
        def save(value):
            tmp=journal.with_suffix('.tmp');descriptor=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            os.fchmod(descriptor,0o600)
            with os.fdopen(descriptor,'w') as stream:json.dump(value,stream)
            tmp.replace(journal)
        def abort():
            flow_id=state.get('flowId')
            if not isinstance(flow_id,str) or not ID.fullmatch(flow_id):return not state
            try:call('/config/config_entries/flow/'+flow_id,method='DELETE')
            except urllib.error.HTTPError as error:
                if error.code!=404:raise
            return True
        if state and (state.get('ownerScope')!=owner or state.get('session')!=session):return base
        if operation=='cancel':
            if state.get('completedEntryId'):return {**base,'status':'configured'}
            if not abort():return base
            save({});return {**base,'status':'cancelled'}
        if state.get('completedEntryId'):
            return {**base,'status':'configured' if any(e['entryId']==state['completedEntryId'] for e in entries) else 'needs_help'}
        if entries and not state.get('inFlight'):return {**base,'status':'existing'}
        if state and now>=state.get('expiresAt',0):
            if operation!='start' or not abort():return base
            save({});state={}
        if operation=='start' and not state:
            if entries:return {**base,'status':'existing'}
            state={'ownerScope':owner,'session':session,'expiresAt':now+TTL,'starting':True,'baselineEntries':[]};save(state)
            flow=call('/config/config_entries/flow',method='POST',payload={'handler':'overkiz','show_advanced_options':False})
            flow_id=flow.get('flow_id') if isinstance(flow,dict) else None
            if not isinstance(flow_id,str) or not ID.fullmatch(flow_id):return base
            state={**state,'flowId':flow_id};state.pop('starting',None);save(state)
            return {**base,**_form(flow)}
        flow_id=state.get('flowId')
        if not isinstance(flow_id,str) or not ID.fullmatch(flow_id):return base
        # A lost POST response must not create a second connection or replay secrets.
        new_entries=[e for e in entries if e['entryId'] not in state.get('baselineEntries',[])]
        if state.get('inFlight') and len(new_entries)==1:
            # A concurrent HA setup could have created it; never attribute an unconfirmed entry.
            return {**base,'status':'existing'}
        flow=call('/config/config_entries/flow/'+flow_id)
        if not isinstance(flow,dict) or flow.get('flow_id')!=flow_id:return base
        form=_form(flow)
        if operation=='start':return {**base,**form}
        if state.get('inFlight') and form['status']!=state.get('submittedStatus'):
            state.pop('inFlight',None);state.pop('submittedStatus',None);save(state)
            return {**base,**form}
        step=flow.get('step_id');values=None
        if operation=='hub' and step=='user' and any(c['id']==payload['hub'] for c in form['choices']):values={'hub':payload['hub']}
        elif operation=='mode' and state.get('selectedHub') in SOMFY and step=='local_or_cloud' and any(c['id']==payload['mode'] for c in form['choices']):values={'api_type':payload['mode']}
        elif operation=='credentials' and state.get('selectedHub') in SOMFY and step=='cloud' and payload['cloudConsent'] is True and isinstance(payload['username'],str) and 1<=len(payload['username'])<=254 and isinstance(payload['password'],str) and 1<=len(payload['password'])<=128:values={'username':payload['username'],'password':payload['password']}
        elif operation=='local' and state.get('selectedHub') in SOMFY and step=='local' and valid_local_host(payload['host']) and payload['verifySsl'] is True and isinstance(payload['token'],str) and 1<=len(payload['token'])<=4096:values={'host':payload['host'],'token':payload['token'],'verify_ssl':True}
        if values is None:return base
        if operation=='hub':state['selectedHub']=payload['hub']
        state.update(inFlight=True,submittedStatus=form['status']);save(state)
        reply=call('/config/config_entries/flow/'+flow_id,method='POST',payload=values)
        if isinstance(reply,dict) and reply.get('type')=='create_entry':
            created=reply.get('result',{});entry_id=created.get('entry_id') if isinstance(created,dict) else None;actual=_entries(call)
            if not isinstance(entry_id,str) or not any(e['entryId']==entry_id for e in actual):return base
            save({'ownerScope':owner,'session':session,'expiresAt':now+TTL,'completedEntryId':entry_id})
            return {**base,'status':'configured','entries':actual}
        if not isinstance(reply,dict) or reply.get('type')=='form' and reply.get('flow_id')!=flow_id:return base
        form=_form(reply);state.pop('inFlight',None);state.pop('submittedStatus',None);save(state)
        return {**base,**form}
