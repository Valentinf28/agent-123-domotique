"""Encrypted, paired-phone LAN access. No HA/admin token is exposed to phones."""
import hashlib, json, os, re, sqlite3, threading, time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote, quote, urlencode
from datetime import datetime
from nacl.secret import SecretBox

FILE=Path('/data/local-mobile-grants.json')
ENTITY=re.compile(r'^[a-z_]+\.[a-z0-9_]{1,180}$')
IDENT=re.compile(r'^[A-Za-z0-9_-]{1,100}$')
SERVICES={
 'switch':{'turn_on','turn_off','toggle'},'light':{'turn_on','turn_off','toggle'},
 'fan':{'turn_on','turn_off','toggle','set_percentage','set_preset_mode'},
 'climate':{'turn_on','turn_off','set_temperature','set_hvac_mode','set_fan_mode','set_preset_mode'},
 'cover':{'open_cover','close_cover','stop_cover','set_cover_position'},
 'lock':{'lock','unlock'},'number':{'set_value'},'select':{'select_option'},
 'button':{'press'},'input_boolean':{'turn_on','turn_off','toggle'},
 'water_heater':{'turn_on','turn_off','set_temperature','set_operation_mode'},
}

def store_grants(value, agent_id, path=FILE):
 if not isinstance(value,dict) or value.get('version')!=1 or value.get('boxId')!=agent_id or not re.fullmatch('[a-f0-9]{64}',value.get('scope','')):raise ValueError('Invalid local phone scope')
 if not isinstance(value.get('installationId'),str) or not IDENT.fullmatch(value['installationId']):raise ValueError('Invalid installation')
 if not isinstance(value.get('phones'),list) or len(value['phones'])>128:raise ValueError('Invalid phone inventory')
 seen=set()
 for phone in value['phones']:
  if not isinstance(phone,dict) or not IDENT.fullmatch(phone.get('id','')) or not re.fullmatch('[a-f0-9]{64}',phone.get('key','')) or phone['id'] in seen:raise ValueError('Invalid phone')
  seen.add(phone['id'])
 for field in ('controls','catalogs'):
  if not isinstance(value.get(field),list) or len(value[field])>2000 or any(not isinstance(x,str) or len(x)>200 for x in value[field]):raise ValueError('Invalid local policy')
 path=Path(path);tmp=path.with_suffix('.tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
 os.replace(tmp,path)

class LocalMobile:
 def __init__(self,call,registry,agent_id,*,path=FILE,ledger=Path('/data/local-mobile-replay.sqlite'),clock=time.time):
  self.call,self.registry,self.agent_id,self.path,self.ledger,self.clock=call,registry,agent_id,Path(path),Path(ledger),clock
  self.cache=None;self.lock=threading.Lock();self.rate={}
 def manifest(self):
  if self.path.is_symlink() or self.path.stat().st_size>200000:raise ValueError('Local access unavailable')
  value=json.loads(self.path.read_text())
  if value.get('boxId')!=self.agent_id():raise ValueError('Local box changed')
  return value
 def policy(self,manifest):
  key=hashlib.sha256(json.dumps([manifest['scope'],manifest['catalogs'],manifest['controls']],sort_keys=True).encode()).hexdigest()
  with self.lock:
   if self.cache and self.cache[0]==key and self.clock()-self.cache[1]<30:return self.cache[2:]
   rows=self.registry({'type':'config/entity_registry/list'})
   if not isinstance(rows,list):raise ValueError('Local equipment unavailable')
   allowed=set(manifest['controls']);hidden=set()
   catalogs=set(manifest['catalogs'])
   for row in rows:
    if not isinstance(row,dict) or row.get('disabled_by'):continue
    entity=row.get('entity_id','');device=row.get('device_id') or entity
    if not ENTITY.fullmatch(entity):continue
    platform=row.get('platform','')
    if platform=='tuya':
     catalog='client-tuya-'+hashlib.sha256(device.encode()).hexdigest()[:40]
     if catalog in catalogs or entity in allowed:allowed.add(entity)
     else:hidden.add(entity)
    elif entity in manifest['controls']:allowed.add(entity)
   self.cache=(key,self.clock(),allowed,hidden)
   return allowed,hidden
 def reserve(self,phone,request_id,digest):
  self.ledger.parent.mkdir(exist_ok=True)
  connection=sqlite3.connect(self.ledger,timeout=5)
  os.chmod(self.ledger,0o600)
  try:
   connection.execute('CREATE TABLE IF NOT EXISTS requests(phone TEXT,id TEXT,digest TEXT,result TEXT,created REAL,PRIMARY KEY(phone,id))')
   connection.execute('BEGIN IMMEDIATE')
   prior=connection.execute('SELECT digest,result FROM requests WHERE phone=? AND id=?',(phone,request_id)).fetchone()
   if prior:
    if prior[0]!=digest:raise ValueError('Request identity changed')
    if prior[1]:return json.loads(prior[1])
    raise ValueError('Previous command result must be checked')
   connection.execute('INSERT INTO requests VALUES(?,?,?,NULL,?)',(phone,request_id,digest,self.clock()))
   connection.execute('DELETE FROM requests WHERE created<?',(self.clock()-86400*7,));connection.commit();return None
  finally:connection.close()
 def finish(self,phone,request_id,packet):
  with sqlite3.connect(self.ledger,timeout=5) as connection:connection.execute('UPDATE requests SET result=? WHERE phone=? AND id=?',(json.dumps(packet),phone,request_id))
 def handle(self,envelope):
  if not isinstance(envelope,dict) or set(envelope)!={'version','phoneId','nonce','ciphertext'} or envelope['version']!=1:raise ValueError('Invalid local request')
  if not IDENT.fullmatch(str(envelope['phoneId'])) or not re.fullmatch('[a-f0-9]{48}',str(envelope['nonce'])) or len(str(envelope['ciphertext']))>1500000:raise ValueError('Invalid local request')
  manifest=self.manifest();phone=next((p for p in manifest['phones'] if p['id']==envelope['phoneId']),None)
  if not phone:raise ValueError('Local phone access revoked')
  now=self.clock()
  with self.lock:
   previous,count=self.rate.get(phone['id'],(now,0));count=count+1 if now-previous<1 else 1;previous=previous if now-previous<1 else now
   if count>20:raise ValueError('Local request rate exceeded')
   self.rate[phone['id']]=(previous,count)
  box=SecretBox(bytes.fromhex(phone['key']));nonce=bytes.fromhex(envelope['nonce'])
  if nonce[0]&128:raise ValueError('Invalid request nonce direction')
  request=json.loads(box.decrypt(bytes.fromhex(envelope['ciphertext']),nonce))
  if not isinstance(request,dict) or request.get('scope')!=manifest['scope'] or request.get('installationId')!=manifest['installationId'] or request.get('requestId')!=envelope['nonce'] or type(request.get('timestamp')) not in (float,int) or abs(now-request['timestamp'])>120:raise ValueError('Stale or foreign local request')
  allowed,hidden=self.policy(manifest);operation=request.get('operation');write=operation=='http' and request.get('method')=='POST'
  prior=None
  if write:prior=self.reserve(phone['id'],request['requestId'],hashlib.sha256(json.dumps(envelope,sort_keys=True).encode()).hexdigest())
  if prior:return prior
  try:
   # Registry lookup may await HA. Recheck revocation and policy before delivery.
   if self.manifest()!=manifest:raise ValueError('Local phone authority changed')
   result=self.dispatch(request,allowed,hidden)
   response={'requestId':request['requestId'],'scope':manifest['scope'],'ok':True,'result':result}
   if len(json.dumps(response))>1900000:raise ValueError('Local response too large')
  except Exception:
   response={'requestId':request['requestId'],'scope':manifest['scope'],'ok':False,'error':'La demande locale a été refusée ou son résultat reste à vérifier.'}
  response_nonce=bytearray(os.urandom(24));response_nonce[0]|=128;response_nonce=bytes(response_nonce)
  packet={'version':1,'nonce':response_nonce.hex(),'ciphertext':box.encrypt(json.dumps(response,separators=(',',':')).encode(),response_nonce).ciphertext.hex()}
  if write:self.finish(phone['id'],request['requestId'],packet)
  return packet
 def dispatch(self,request,allowed,hidden):
  if request.get('operation')=='websocket':
   command=request.get('command',{})
   if not isinstance(command,dict) or command.get('type') not in ('recorder/statistics_during_period','history/statistics_during_period') or set(command)-{'type','start_time','end_time','statistic_ids','period','types'}:raise ValueError('Unsupported local statistics')
   ids=command.get('statistic_ids')
   if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(x,str) or not ENTITY.fullmatch(x) or x in hidden for x in ids):raise ValueError('Invalid statistics scope')
   return self.registry(command)
  if request.get('operation')!='http':raise ValueError('Unsupported local operation')
  method=request.get('method');path=request.get('path');body=request.get('body')
  if not isinstance(path,str) or len(path)>3000 or '\\' in path:raise ValueError('Invalid local path')
  parsed=urlsplit(path)
  if parsed.scheme or parsed.netloc or parsed.fragment:raise ValueError('Foreign local path')
  if method=='GET' and parsed.path=='/states' and not parsed.query:
   states=self.call('/states')
   return [s for s in states if isinstance(s,dict) and s.get('entity_id') not in hidden]
  if method=='GET' and re.fullmatch(r'/history/period/[^/]{10,90}',parsed.path):
   query=parse_qs(parsed.query,keep_blank_values=True,strict_parsing=True)
   if set(query)-{'filter_entity_id','minimal_response','end_time'} or any(len(v)!=1 for v in query.values()):raise ValueError('Invalid local history')
   ids=query.get('filter_entity_id',[''])[0].split(',')
   if len(ids)>100 or any(not ENTITY.fullmatch(x) or x in hidden for x in ids):raise ValueError('Invalid history scope')
   start=unquote(parsed.path.removeprefix('/history/period/'))
   datetime.fromisoformat(start.replace('Z','+00:00'))
   if '/' in start or not re.fullmatch(r'[0-9TtZz:+. -]{10,60}',start):raise ValueError('Invalid history date')
   if 'end_time' in query:datetime.fromisoformat(query['end_time'][0].replace('Z','+00:00'))
   safe_path='/history/period/'+quote(start,safe='')+'?'+urlencode({k:v[0] for k,v in query.items()})
   return self.call(safe_path)
  match=re.fullmatch(r'/services/([a-z_]+)/([a-z_]+)',parsed.path)
  if method=='POST' and match and not parsed.query:
   domain,service=match.groups()
   if service not in SERVICES.get(domain,set()) or not isinstance(body,dict) or set(body)&{'area_id','device_id','target'}:raise ValueError('Unsupported local command')
   ids=body.get('entity_id');ids=[ids] if isinstance(ids,str) else ids
   if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(x,str) or not ENTITY.fullmatch(x) or x not in allowed or x in hidden or x.split('.')[0]!=domain for x in ids):raise ValueError('Command not assigned to this installation')
   for field,value in body.items():
    if field!='entity_id' and (not isinstance(value,(str,int,float,bool,list)) or len(json.dumps(value))>1000):raise ValueError('Invalid command value')
   return self.call(parsed.path,method='POST',payload=body)
  raise ValueError('Unsupported local endpoint')
