"""Offline per-device maintenance credential and bounded failed-attempt persistence."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time

ITERATIONS=600_000

class Refused(Exception):pass

def normalize(code):
    if not isinstance(code,str) or len(code)>40:return None
    code=code.replace('-','').replace(' ','')
    return code if re.fullmatch('[0-9]{24}',code) else None

def generate(machine_id):
    if not re.fullmatch('[a-f0-9]{32}',machine_id):raise Refused('identite_machine_invalide')
    code=''.join(str(secrets.randbelow(10)) for _ in range(24));salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',(machine_id+'\0'+code).encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return {'machine_id':machine_id,'credential_hash':f'pbkdf2-sha256${ITERATIONS}${salt}${digest}'},'-'.join(code[i:i+4] for i in range(0,24,4))

def valid_configuration(options,actual_machine):
    if options.get('machine_id')!=actual_machine or not re.fullmatch('[a-f0-9]{32}',actual_machine):raise Refused('identite_machine_differente')
    if not re.fullmatch(r'pbkdf2-sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}',options.get('credential_hash','')):raise Refused('code_atelier_non_prepare')

def verify(options,code):
    normalized=normalize(code)
    if normalized is None:return False
    _,iterations,salt,expected=options['credential_hash'].split('$')
    digest=hashlib.pbkdf2_hmac('sha256',(options['machine_id']+'\0'+normalized).encode(),bytes.fromhex(salt),int(iterations)).hex()
    return hmac.compare_digest(digest,expected)

def save(path,value):
    path=Path(path);temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)

class Attempts:
    def __init__(self,path,boot_id,clock=time.monotonic):
        self.path=Path(path);self.clock=clock
        self.data=json.loads(self.path.read_text()) if self.path.exists() else {'failures':0,'until':0,'boot':boot_id}
        if self.data['boot']!=boot_id:
            self.data.update(boot=boot_id,until=clock()+600 if self.data['failures']>=5 else 0);save(self.path,self.data)
    def remaining(self):return max(0,int(self.data['until']-self.clock()+.999))
    def failed(self):
        failures=min(20,self.data['failures']+1)
        self.data.update(failures=failures,until=self.clock()+(min(600,60*2**(failures-5)) if failures>=5 else 2))
        save(self.path,self.data)
    def succeeded(self):
        self.data.update(failures=0,until=0);save(self.path,self.data)
