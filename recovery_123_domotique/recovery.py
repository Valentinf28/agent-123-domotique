"""Independent recovery app. Outbound HTTPS only, no HA Core imports or proxy.

The protocol grants a short, single operation, never an arbitrary URL, shell,
file write, HA service, restore, host command or change to another add-on.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import threading
import time
import urllib.request
import uuid
from archive_verify import verify_supervisor_archive

VERSION = '0.1.0'
ORIGIN = 'https://home.123panneaux-solaires.fr'
REPOS = {hashlib.sha1(s.lower().encode()).hexdigest()[:8] for s in (
    'https://github.com/Valentinf28/agent-123-domotique',
    'https://github.com/Valentinf28/agent-123-domotique#codex/automatic-box-relay')}
UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
SEMVER = re.compile(r'(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})')

class Refused(RuntimeError): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): raise Refused('REDIRECT_REFUSED')

def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        if os.fstat(f.fileno()).st_size > 262144: raise Refused('STATE_TOO_LARGE')
        result = json.load(f)
        if not isinstance(result, dict): raise Refused('STATE_INVALID')
        return result

def save_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

class Transport:
    def __init__(self, credential, supervisor_token):
        if not re.fullmatch('[a-f0-9]{64}', credential): raise Refused('AUTH_INVALID')
        self.credential, self.supervisor_token = credential, supervisor_token
        self.opener = urllib.request.build_opener(NoRedirect())
    def request(self, method, path, body=None, *, supervisor=False):
        if supervisor:
            read = method == 'GET' and (path in ('/addons/self/info', '/core/info', '/jobs/info') or re.fullmatch(r'/addons/[a-f0-9]{8}_agent_123_domotique/info', path) or re.fullmatch(r'/backups/[A-Za-z0-9_-]{1,80}/info', path) or re.fullmatch(r'/jobs/(?:[a-f0-9]{32}|[a-f0-9-]{36})', path))
            write = method == 'POST' and re.fullmatch(r'/addons/[a-f0-9]{8}_agent_123_domotique/(?:restart|start|update)', path)
            if not (read or write): raise Refused('SUPERVISOR_PATH_REFUSED')
            # Defense in depth even when called outside Engine.
            m = re.match(r'/addons/([a-f0-9]{8})_agent_', path)
            if m and m[1] not in REPOS: raise Refused('REPOSITORY_REFUSED')
            origin, token = 'http://supervisor', self.supervisor_token
        else:
            if method != 'POST' or not re.fullmatch(r'/api/device/recovery/(?:poll|[a-f0-9-]{36}/(?:permit|result))', path): raise Refused('PORTAL_PATH_REFUSED')
            origin, token = ORIGIN, self.credential
        if not token or '\r' in token or '\n' in token: raise Refused('AUTH_UNAVAILABLE')
        request = urllib.request.Request(origin+path, method=method,
            data=json.dumps(body or {}).encode() if method == 'POST' else None,
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=25) as response:
            raw = response.read(262145)
            if len(raw)>262144: raise Refused('RESPONSE_TOO_LARGE')
            result = json.loads(raw)
            if not isinstance(result, dict): raise Refused('RESPONSE_INVALID')
            if supervisor:
                if result.get('result') != 'ok' or not isinstance(result.get('data'), dict): raise Refused('SUPERVISOR_REFUSED')
                return result['data']
            return result
    def portal(self, path, body): return self.request('POST', '/api/device/recovery/'+path, body)
    def native(self, path, method='GET', body=None): return self.request(method, path, body, supervisor=True)

class Engine:
    def __init__(self, http, *, data=Path('/data'), clock=time.time, verify=None):
        self.http, self.data, self.clock = http, Path(data), clock
        self.verify = verify or (lambda slug: verify_supervisor_archive(slug, http.supervisor_token))
        self.path = self.data/'recovery-journal.json'
        self.binding = hashlib.sha256(http.credential.encode()).hexdigest()
        self.boot_id = str(uuid.uuid4())
    def load(self):
        if not self.path.exists(): return {}
        value = read_private(self.path)
        # Never resume an operation from a retired installation's credential.
        return value if value.get('binding') == self.binding else {}
    def save(self, state):
        state['binding'] = self.binding
        save_private(self.path, state)
        if state.get('command',{}).get('id') and UUID.fullmatch(state['command']['id']):
            save_private(self.data/'operations'/(state['command']['id']+'.json'), state)
    def target(self):
        own = self.http.native('/addons/self/info')
        repo = own.get('repository')
        if repo not in REPOS or own.get('slug') != repo+'_recovery_123_domotique': raise Refused('RECOVERY_SOURCE_REFUSED')
        slug = repo+'_agent_123_domotique'
        agent = self.http.native('/addons/'+slug+'/info')
        if agent.get('slug') != slug or agent.get('repository') != repo or agent.get('state') not in ('started','stopped','error'): raise Refused('AGENT_SOURCE_REFUSED')
        return slug, agent
    def snapshot(self):
        result = {'supervisor': False, 'agentState': 'unknown', 'agentVersion': None, 'coreVersion': None, 'coreState': 'unknown', 'nativeIdle': False}
        try:
            _, agent = self.target()
            result.update(supervisor=True, agentState=agent['state'], agentVersion=agent.get('version'))
        except Exception: pass
        try:
            core = self.http.native('/core/info')
            result.update(coreVersion=core.get('version'), coreState=core.get('state', 'unknown'))
        except Exception: pass
        try:
            self.idle(); result['nativeIdle'] = True
        except Exception: pass
        return result
    def idle(self):
        result = self.http.native('/jobs/info')
        if not isinstance(result.get('jobs'), list): raise Refused('NATIVE_JOBS_UNKNOWN')
        def active(j):
            if not isinstance(j, dict): raise Refused('NATIVE_JOBS_UNKNOWN')
            # Completed jobs are history; no normal maintenance journal is consulted.
            if j.get('done') is not True: return True
            return any(active(child) for child in j.get('child_jobs', []))
        if any(active(j) for j in result['jobs']): raise Refused('NATIVE_OPERATION_RUNNING')
    def valid(self, command):
        if not isinstance(command, dict) or set(command) != {'id','action','payload','expiresAt'} or not isinstance(command['id'], str) or not UUID.fullmatch(command['id']): raise Refused('COMMAND_INVALID')
        if type(command['expiresAt']) not in (int,float) or not self.clock()*1000 < command['expiresAt'] <= (self.clock()+600)*1000: raise Refused('COMMAND_EXPIRED')
        action, payload = command['action'], command['payload']
        if action not in ('diagnostic','agent.restart','agent.update') or not isinstance(payload, dict): raise Refused('ACTION_REFUSED')
        if action == 'agent.update':
            if set(payload) != {'version','commit','backupSlug'} or not isinstance(payload['version'],str) or not SEMVER.fullmatch(payload['version']) or not isinstance(payload['commit'],str) or not re.fullmatch('[a-f0-9]{40}',payload['commit']) or not isinstance(payload['backupSlug'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',payload['backupSlug']): raise Refused('RELEASE_INVALID')
        elif payload: raise Refused('PAYLOAD_REFUSED')
    def permit(self, command):
        self.valid(command)
        result = self.http.portal(command['id']+'/permit', {'command': command})
        if result.get('allowed') is not True: raise Refused('AUTHORIZATION_WITHDRAWN')
    def report(self, state):
        self.http.portal(state['command']['id']+'/result', {'state': state['state'], 'diagnostics': self.snapshot(), 'proof': state.get('proof', {})})
    def reconcile(self, state):
        if state.get('state') not in ('submitted','uncertain'): return state
        # Observation only: a lost response never resubmits a mutation.
        slug, agent = self.target()
        command = state['command']
        done = False
        if command['action'] == 'agent.update':
            done = agent.get('version') == command['payload']['version'] and agent.get('state') == 'started'
        elif state.get('accepted'):
            if state.get('jobId'):
                job = self.http.native('/jobs/'+state['jobId'])
                done = job.get('done') is True and not job.get('errors') and agent.get('state') == 'started'
            else:
                done = agent.get('state') == 'started'
        if done:
            state['state'] = 'completed'; self.save(state)
        elif self.clock()-state['submittedAt'] > 1200:
            state['state'] = 'uncertain'; self.save(state)
        return state
    def execute(self, command):
        self.valid(command)
        prior = self.load()
        history = self.data/'operations'/(command['id']+'.json')
        if history.exists():
            old = read_private(history)
            if old.get('binding') == self.binding:
                self.report(self.reconcile(old)); return
        if prior.get('command',{}).get('id') == command['id']:
            # Completed, refused and uncertain operations are never replayed either.
            self.report(self.reconcile(prior)); return
        if prior.get('state') in ('preparing','submitted'):
            # Only a NEW server-authorized request may follow an expired operation.
            # Closing uncertainty never turns the older operation into a success.
            if prior.get('command',{}).get('expiresAt',float('inf')) >= self.clock()*1000:
                raise Refused('RECOVERY_ALREADY_RUNNING')
            self.idle(); self.permit(command)
            prior['state']='uncertain'; self.save(prior)
        state = {'command': command, 'state': 'preparing'}
        self.save(state)
        try:
            self.permit(command)
            slug, agent = self.target()
            if command['action'] == 'diagnostic':
                state['state'] = 'completed'; self.save(state); self.report(state); return
            self.idle()
            if command['action'] == 'agent.update':
                p = command['payload']
                if agent.get('version_latest') != p['version'] or agent.get('version') == p['version'] or agent.get('auto_update') is not False: raise Refused('NATIVE_VERSION_CHANGED')
                if not SEMVER.fullmatch(str(agent.get('version',''))) or tuple(map(int,p['version'].split('.'))) <= tuple(map(int,agent['version'].split('.'))): raise Refused('DOWNGRADE_REFUSED')
                info = self.http.native('/backups/'+p['backupSlug']+'/info')
                if info.get('slug') != p['backupSlug'] or info.get('type') != 'full' or info.get('homeassistant_exclude_database') is not False or not any(a.get('slug') == slug for a in info.get('addons',info.get('apps',[]))): raise Refused('FULL_BACKUP_REQUIRED')
                proof = self.verify(p['backupSlug'])
                if proof.get('verified') is not True or slug not in proof.get('addons',[]): raise Refused('BACKUP_NOT_VERIFIED')
                state['proof'] = {'backupVerified': True, 'backupSlug': p['backupSlug'], 'sha256': proof['sha256'], 'bytes': proof['bytes']}
                self.save(state)
                # Revalidate current consent and native store immediately after a long archive read.
                self.permit(command); self.idle()
                _, current = self.target()
                if any(current.get(k) != agent.get(k) for k in ('version','version_latest','auto_update')): raise Refused('NATIVE_VERSION_CHANGED')
                endpoint = 'update'
            else:
                self.permit(command)
                endpoint = 'start' if agent.get('state') != 'started' else 'restart'
            # Durable intent BEFORE the side effect, and commit gate immediately before submission.
            self.permit(command)
            state.update(state='submitted', submittedAt=self.clock(), beforeVersion=agent.get('version'))
            self.save(state)
            response = self.http.native('/addons/'+slug+'/'+endpoint, 'POST', {'background': True, **({'version': command['payload']['version']} if endpoint == 'update' else {})})
            state.update(accepted=True, jobId=response.get('job_id'))
            self.save(state)
            self.report(self.reconcile(state))
        except Exception:
            # The client never receives raw exception/response text (may contain secrets).
            if state['state'] != 'submitted': state['state'] = 'refused'
            self.save(state)
            try: self.report(state)
            except Exception: pass
    def tick(self):
        state = self.load()
        if state.get('state') == 'preparing':
            # Restart during preparation needs a new SAV request; never silently resume.
            state['state'] = 'uncertain'; self.save(state)
        if state:
            try: self.report(self.reconcile(state))
            except Exception: pass
        result = self.http.portal('poll', {'version':VERSION,'bootId':self.boot_id,'diagnostics':self.snapshot()})
        if result.get('command'): self.execute(result['command'])

def main():
    stop=threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    options=read_private(Path('/data/options.json'))
    if not isinstance(options.get('device_id'),str) or not UUID.fullmatch(options['device_id']): raise Refused('DEVICE_INVALID')
    engine=Engine(Transport(options.get('credential',''),os.environ.get('SUPERVISOR_TOKEN','')))
    while not stop.is_set():
        try: engine.tick()
        except Exception: pass  # No credentials, network details or customer data in logs.
        stop.wait(15)

if __name__=='__main__': main()
