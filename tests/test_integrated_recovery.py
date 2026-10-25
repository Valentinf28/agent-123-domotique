"""Recovery must survive absent/broken Core and main agent, without Tailscale."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'recovery_123_domotique'))
from recovery import Engine, Transport, Refused, NativeRefused, REPOS

class Fake:
    credential='a'*64
    supervisor_token='internal'
    def __init__(self):
        self.repo=sorted(REPOS)[0];self.posts=[];self.allowed=True;self.fail_after_submit=False
        self.agent={'repository':self.repo,'slug':self.repo+'_agent_123_domotique','version':'0.6.48','version_latest':'0.6.49','state':'started','auto_update':False}
        self.pending=[];self.reports=[];self.command=None;self.core_down=False
    def native(self,path,method='GET',body=None):
        if path=='/addons/self/info':return {'slug':self.repo+'_recovery_123_domotique','repository':self.repo}
        if path=='/addons/'+self.agent['slug']+'/info':return dict(self.agent)
        if path=='/core/info':
            if self.core_down:raise ConnectionError()
            return {'version':'2026.10.3','state':'running'}
        if path=='/jobs/info':return {'jobs':self.pending}
        if path.startswith('/jobs/'):return {'done':True,'errors':[]}
        if path=='/backups/99d90950/info':return {'slug':'99d90950','type':'full','homeassistant_exclude_database':False,'addons':[{'slug':self.agent['slug']}]}
        if method=='POST':
            self.posts.append((path,body))
            if self.fail_after_submit:raise TimeoutError()
            return {'job_id':'b'*32}
        raise AssertionError(path)
    def portal(self,path,body):
        if path=='poll':return {'command':self.command}
        if path.endswith('/permit'):
            if not self.allowed:raise Refused('AUTHORIZATION_WITHDRAWN')
            return {'allowed':True}
        if path.endswith('/result'):self.reports.append(body);return {'received':True}
        raise AssertionError(path)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name);self.f=Fake()
        self.now=1_800_000_000
        self.engine=Engine(self.f,data=self.data,clock=lambda:self.now,verify=lambda slug:{'verified':True,'addons':[self.f.agent['slug']],'sha256':'b'*64,'bytes':12000})
    def cmd(self,action='agent.restart',payload=None):return {'id':str(uuid.uuid4()),'action':action,'payload':payload or {},'expiresAt':(self.now+590)*1000}
    def update(self):return self.cmd('agent.update',{'version':'0.6.49','commit':'c'*40,'backupSlug':'99d90950'})
    def test_core_and_agent_may_be_down_without_blocking_recovery(self):
        self.f.core_down=True;self.f.agent['state']='error';self.engine.execute(self.cmd())
        self.assertEqual(self.f.posts[0][0],'/addons/'+self.f.agent['slug']+'/start')
        self.assertEqual(self.engine.load()['state'],'submitted')
        self.f.agent['state']='started';self.engine.tick();self.assertEqual(self.engine.load()['state'],'completed')
    def test_main_maintenance_journal_and_broken_main_import_are_not_dependencies(self):
        (self.data/'core-update.json').write_text('{"state":"attention_required"}')
        (self.data/'agent.py').write_text('invalid python !!!')
        self.engine.execute(self.cmd());self.assertEqual(len(self.f.posts),1)
    def test_restart_is_confirmed_from_native_job(self):
        self.engine.execute(self.cmd());self.assertEqual(self.engine.load()['state'],'completed')
    def test_permission_withdrawn_blocks_restart(self):
        self.f.allowed=False;self.engine.execute(self.cmd());self.assertFalse(self.f.posts)
    def test_active_native_job_blocks_restart_even_if_main_journal_missing(self):
        self.f.pending=[{'done':False}];self.engine.execute(self.cmd());self.assertFalse(self.f.posts)
    def test_lost_mutation_response_never_replays_on_restart_or_redelivery(self):
        self.f.fail_after_submit=True;c=self.cmd();self.engine.execute(c)
        self.assertEqual(self.engine.load()['state'],'submitted')
        second=Engine(self.f,data=self.data,clock=lambda:self.now)
        second.execute(c);second.tick();self.assertEqual(len(self.f.posts),1)
        self.now+=1201;second.tick();self.assertEqual(second.load()['state'],'uncertain')
        with self.assertRaises(Refused):second.execute(c)
        self.assertEqual(len(self.f.posts),1)
    def test_older_command_is_not_replayed_after_other_command(self):
        c=self.cmd();self.engine.execute(c);self.engine.execute(self.cmd());self.engine.execute(c)
        self.assertEqual(len(self.f.posts),2)
    def test_expired_or_extra_arbitrary_fields_rejected(self):
        for change in [{'expiresAt':self.now*1000},{'url':'https://evil.example'},{'action':'shell'},{'payload':{'command':'rm -rf'}}]:
            c=self.cmd();c.update(change)
            with self.assertRaises(Refused):self.engine.execute(c)
        self.assertFalse(self.f.posts)
    def test_only_official_repo_target_is_allowed(self):
        self.f.repo='deadbeef';self.engine.execute(self.cmd());self.assertFalse(self.f.posts)
    def test_update_reads_archive_and_confirms_actual_version_not_ack(self):
        self.engine.execute(self.update());self.assertEqual(self.engine.load()['state'],'submitted');self.assertEqual(self.f.posts[0][1],{'background':True,'backup':False})
        self.assertEqual(self.engine.load()['proof']['backupVerified'],True)
        self.f.agent['version']='0.6.49';self.engine.tick();self.assertEqual(self.engine.load()['state'],'completed')
    def test_update_failure_or_wrong_backup_blocks_install(self):
        for proof in [{'verified':False},{'verified':True,'addons':['other']}]:
            with tempfile.TemporaryDirectory() as d:
                e=Engine(self.f,data=Path(d),clock=lambda:self.now,verify=lambda _:proof)
                e.execute(self.update());self.assertFalse(self.f.posts)
    def test_consent_is_rechecked_after_reading_large_backup(self):
        def verify(_):self.f.allowed=False;return {'verified':True,'addons':[self.f.agent['slug']],'sha256':'b'*64,'bytes':12000}
        self.engine.verify=verify;self.engine.execute(self.update());self.assertFalse(self.f.posts)
    def test_catalog_or_auto_update_changes_refuse_install(self):
        for key,value in [('version_latest','0.6.50'),('auto_update',True)]:
            with tempfile.TemporaryDirectory() as d:
                previous=self.f.agent[key];self.f.agent[key]=value
                Engine(self.f,data=Path(d),clock=lambda:self.now).execute(self.update());self.assertFalse(self.f.posts);self.f.agent[key]=previous
    def test_definitive_native_rejection_does_not_leave_an_uncertain_install(self):
        original=self.f.native
        def native(path,method='GET',body=None):
            if method=='POST':raise NativeRefused('NATIVE_REFUSED')
            return original(path,method,body)
        self.f.native=native;self.engine.execute(self.update())
        self.assertEqual(self.engine.load()['state'],'refused')
        self.assertEqual(self.engine.load()['proof']['failureCode'],'native_refused')
    def test_http_4xx_is_a_definitive_refusal_but_timeout_stays_uncertain(self):
        class Opener:
            def open(self,*args,**kwargs):raise urllib.error.HTTPError('http://supervisor',400,'Bad request',{},None)
        t=Transport('a'*64,'internal');t.opener=Opener()
        with self.assertRaises(NativeRefused):t.native('/addons/'+self.f.agent['slug']+'/update','POST',{'background':True,'backup':False})
    def test_new_owner_rekeys_without_inheriting_prior_owner_device_id(self):
        sys.path.insert(0,str(ROOT/'agent_123_domotique'))
        from recovery_setup import provision
        seen=[]
        def register(body):seen.append(body);return {'registered':False,'rotate':True}
        with patch('installation_reset.blocks_mutations',return_value=False):provision('primary'*10,lambda *a,**kw:self.fail('No native write before rekey'),data=self.data,register=register)
        saved=json.loads((self.data/'recovery-enrollment.json').read_text())
        self.assertNotEqual(saved['deviceId'],seen[0]['deviceId']);self.assertNotEqual(saved['credential'],seen[0]['credential'])
    def test_state_durable_and_private_before_submission(self):
        def submit(path,method='GET',body=None):
            if method=='POST':self.assertEqual(json.loads(self.engine.path.read_text())['state'],'submitted');raise TimeoutError()
            return original(path,method,body)
        original=self.f.native;self.f.native=submit;self.engine.execute(self.cmd())
        self.assertEqual(self.engine.path.stat().st_mode&0o777,0o600)
    def test_corrupt_journal_fails_closed(self):
        self.engine.path.write_text('broken')
        with self.assertRaises(Exception):self.engine.execute(self.cmd())
        self.assertFalse(self.f.posts)
    def test_transport_has_no_proxy_shell_restore_or_network_option(self):
        t=Transport('a'*64,'internal')
        for path in ['/core/restart','/os/update','/backups/full/restore','/addons/core_ssh/restart','/addons/deadbeef_agent_123_domotique/update','https://evil.example','/network/interface/wlan0/update']:
            with self.assertRaises(Refused):t.request('POST',path,{},supervisor=True)
        for path in ['/api/agent/heartbeat','/api/device/recovery/../../proxy']:
            with self.assertRaises(Refused):t.request('POST',path,{})
    def test_provisioning_has_separate_secret_and_does_not_repeat_uncertain_install(self):
        sys.path.insert(0,str(ROOT/'agent_123_domotique'))
        from recovery_setup import provision
        calls=[];repo=sorted(REPOS)[0]
        def native(path,**kw):
            if path=='/addons/self/info':return {'slug':repo+'_agent_123_domotique','repository':repo}
            if path.endswith('/info'):return {'slug':repo+'_recovery_123_domotique','repository':repo,'version_latest':'0.1.1','state':'unknown'}
            calls.append(path);raise TimeoutError()
        seen=[]
        def register(body):seen.append(body);return {'registered':True}
        with patch('installation_reset.blocks_mutations',return_value=False):
            with self.assertRaises(TimeoutError):provision('primary'*10,native,data=self.data,register=register)
            provision('primary'*10,native,data=self.data,register=register)
        self.assertEqual(len(calls),1);self.assertEqual(seen[0],seen[1]);self.assertNotEqual(seen[0]['credential'],'primary'*10)

if __name__=='__main__':unittest.main()
