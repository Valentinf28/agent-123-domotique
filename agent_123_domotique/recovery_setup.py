"""Provision the independent recovery app once, before software maintenance.

Uses the enrolled agent credential only to register a distinct recovery secret.
The guardian never receives the main agent token. Failures cannot affect normal
heartbeat, and installation requests with a lost response are not replayed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.request
import uuid

ORIGIN='https://home.123panneaux-solaires.fr'
SOURCES=('https://github.com/Valentinf28/agent-123-domotique','https://github.com/Valentinf28/agent-123-domotique#codex/automatic-box-relay')
REPOS={hashlib.sha1(s.lower().encode()).hexdigest()[:8] for s in SOURCES}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise RuntimeError('Recovery redirect refused')

def provision(primary, native, *, data=Path('/data'), register=None):
    if not isinstance(primary,str) or len(primary)<40:raise RuntimeError('Not enrolled')
    from installation_reset import blocks_mutations
    if blocks_mutations(data):return  # never introduce an installation in the middle of another maintenance
    path=Path(data)/'recovery-enrollment.json';binding=hashlib.sha256(primary.encode()).hexdigest()
    saved=json.loads(path.read_text()) if path.exists() else {}
    if saved.get('binding')!=binding:
        saved={'binding':binding,'credential':secrets.token_hex(32),'deviceId':str(uuid.uuid4())}
        write(path,saved)
    if register is None:
        def register(body):
            req=urllib.request.Request(ORIGIN+'/api/agent/recovery',method='POST',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+primary,'Content-Type':'application/json'})
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as r:
                value=r.read(8193)
                if len(value)>8192:raise RuntimeError('Recovery registration too large')
                return json.loads(value)
    reply=register({'deviceId':saved['deviceId'],'credential':saved['credential']})
    if reply.get('registered') is not True:raise RuntimeError('Registration refused')
    own=native('/addons/self/info');repo=own.get('repository')
    if repo not in REPOS or own.get('slug')!=repo+'_agent_123_domotique':raise RuntimeError('Source refused')
    slug=repo+'_recovery_123_domotique'
    info=native('/addons/'+slug+'/info')
    if info.get('slug')!=slug or info.get('repository')!=repo or info.get('version_latest')!='0.1.0':raise RuntimeError('Recovery catalog not qualified')
    if info.get('state')=='unknown':
        if saved.get('installSubmitted'):return  # Operator must inspect an uncertain native install.
        saved['installSubmitted']=True;write(path,saved)
        native('/addons/'+slug+'/install',method='POST',payload={'background':True},timeout=30)
        return
    if info.get('version')!='0.1.0' or info.get('boot')!='auto' or info.get('auto_update') is not False:raise RuntimeError('Recovery installation not qualified')
    options={'credential':saved['credential'],'device_id':saved['deviceId']}
    if info.get('options')!=options:
        native('/addons/'+slug+'/options',method='POST',payload={'options':options})
        if info.get('state')=='started':native('/addons/'+slug+'/restart',method='POST',payload={'background':True})
    elif info.get('state')!='started':native('/addons/'+slug+'/start',method='POST',payload={'background':True})

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def start(primary,native,*,data=Path('/data')):
    def loop():
        while True:
            try:provision(primary(),native,data=data)
            except Exception:pass
            time.sleep(60)
    threading.Thread(target=loop,daemon=True,name='recovery-enrollment').start()
