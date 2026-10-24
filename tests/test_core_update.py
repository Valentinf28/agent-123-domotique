import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from core_update import CoreUpdate, busy, version

O='a'*64;R='b'*64;ID='11111111-1111-4111-8111-111111111111';C='22222222-2222-4222-8222-222222222222'
class Fake:
    def __init__(self):
        self.current='2026.7.2';self.latest='2026.10.4';self.calls=[];self.fail_update=False;self.fail_check=False;self.low=False;self.unhealthy=False
        self.states=[{'entity_id':'switch.ballon','state':'off'},{'entity_id':'sensor.pv','state':'20'},{'entity_id':'automation.ballon','state':'on'}]
        self.entries=[{'entry_id':'e1','domain':'shelly','state':'loaded'}]
        self.backups=[];self.now=1800000000
    def call(self,p,**kw):
        self.calls.append(('ha',p,kw))
        if p=='/config':return {'version':self.current,'state':'RUNNING'}
        if p=='/states':return copy.deepcopy(self.states)
        if p=='/config/config_entries/entry':return copy.deepcopy(self.entries)
        raise ValueError(p)
    def supervisor(self,p,**kw):
        self.calls.append(('sup',p,kw))
        if p=='/core/info':return {'version':self.current,'version_latest':self.latest,'image':'ghcr.io/home-assistant/qemux86-64-homeassistant','arch':'amd64'}
        if p=='/supervisor/info':return {'healthy':not self.unhealthy,'supported':True,'channel':'stable'}
        if p=='/core/check':
            if self.fail_check:raise RuntimeError('bad configuration')
            return {}
        if p=='/core/update':
            if self.fail_update:raise TimeoutError()
            return {'job_id':'j1'}
        if p=='/backups':return {'backups':copy.deepcopy(self.backups)}
        if p.startswith('/backups/') and p.endswith('/info'):
            slug=p.split('/')[2];b=next(b for b in self.backups if b['slug']==slug)
            return {**b,'type':'full','homeassistant':self.current,'homeassistant_exclude_database':False,'size':1,'addons':[{'slug':'own'}]}
        if p=='/addons/self/info':return {'slug':'own'}
        if p=='/backups/new/full':
            b={'slug':'newbackup','name':kw['payload']['name'],'date':datetime.fromtimestamp(self.now,timezone.utc).isoformat()};self.backups.append(b);return {'slug':'newbackup'}
        raise ValueError(p)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.f=Fake();self.queue=[]
        self.e=CoreUpdate(self.f.call,self.f.supervisor,lambda slug:{'verified':True,'sha256':'c'*64,'addons':['own']},registry=lambda:None,authorize=lambda:{'is_admin':True},data=self.data,clock=lambda:self.f.now,sleep=lambda n:None,free_bytes=lambda:1 if self.f.low else 10*1024**3)
        self.e.start=lambda method,identifier:self.queue.append((method,identifier))
    def tearDown(self):self.tmp.cleanup()
    def prep(self,slug=None):
        p={'operation':'prepare','ownerScope':O,'operationId':ID,'consentId':C,'releaseId':R,'targetVersion':'2026.10.4','backupSlug':slug,'backupLimit':2}
        self.e.command(p);method,i=self.queue.pop();method(i);return self.e.load()
    def execute(self,s):
        p={k:s[k] for k in ('operationId','consentId','releaseId','targetVersion')};p.update(operation='execute',ownerScope=O,confirmed=True,previewHash=s['previewHash'])
        self.e.command(p);method,i=self.queue.pop();method(i);return self.e.load()
    def test_pinned_install_and_actual_postchecks(self):
        s=self.execute(self.prep());self.assertEqual(s['state'],'verifying');self.assertTrue(s['backupVerified']);self.assertTrue(busy(self.data))
        updates=[x for x in self.f.calls if x[1]=='/core/update'];self.assertEqual(len(updates),1);self.assertEqual(updates[0][2]['payload'],{'version':'2026.10.4','backup':False,'background':True})
        self.f.current='2026.10.4';s=self.e.observe(s);self.assertEqual(s['state'],'completed');self.assertTrue(all(s['checks'].values()));self.assertFalse(busy(self.data))
    def test_acknowledgement_is_not_completion(self):
        s=self.execute(self.prep());self.assertEqual(self.e.observe(s)['state'],'verifying')
    def test_lost_install_response_is_never_replayed(self):
        self.f.fail_update=True;s=self.execute(self.prep());self.e.observe(s);self.assertEqual(len([x for x in self.f.calls if x[1]=='/core/update']),1)
        p={k:s[k] for k in ('operationId','consentId','releaseId','targetVersion')};p.update(operation='execute',ownerScope=O,confirmed=True,previewHash=s['previewHash']);self.e.command(p);self.assertFalse(self.queue)
    def test_preexisting_failure_is_reported_and_not_conflated_with_regression(self):
        self.f.entries[0]['state']='setup_error';s=self.prep();self.assertEqual(s['state'],'prepared');self.assertEqual(s['inventory']['existingFailures'],[{'id':'e1','domain':'shelly','state':'setup_error'}])
        s=self.execute(s);self.f.current='2026.10.4';self.assertEqual(self.e.observe(s)['state'],'completed')
    def test_changed_inventory_prevents_install(self):
        s=self.prep();self.f.states.pop();self.assertEqual(self.execute(s)['state'],'failed');self.assertFalse([x for x in self.f.calls if x[1]=='/core/update'])
    def test_configuration_check_failure(self):
        self.f.fail_check=True;self.assertEqual(self.prep()['state'],'failed')
    def test_capacity_refuses_without_deletion(self):
        self.f.backups=[{'slug':'old1'},{'slug':'old2'}];s=self.execute(self.prep());self.assertEqual(s['state'],'failed');self.assertFalse([x for x in self.f.calls if x[1]=='/core/update' or 'DELETE'==x[2].get('method')])
    def test_expired_preview(self):
        s=self.prep();self.f.now+=901
        with self.assertRaises(RuntimeError):self.execute(s)
    def test_foreign_owner_and_target(self):
        self.prep()
        with self.assertRaises(RuntimeError):self.e.command({'operation':'status','ownerScope':'d'*64,'operationId':ID})
    def test_official_stable_only_and_forward(self):
        for v in ['latest','2026.10.0b1','http://evil','2026.10.04']:
            with self.assertRaises(ValueError):version(v)
        with self.assertRaises(RuntimeError):self.e.inspect('2026.6.3')
    def test_low_disk_and_unhealthy(self):
        self.f.low=True
        with self.assertRaises(RuntimeError):self.e.inspect()
        self.f.low=False;self.f.unhealthy=True
        with self.assertRaises(RuntimeError):self.e.inspect()
    def test_post_update_entities_and_automations_checked(self):
        s=self.execute(self.prep());self.f.current='2026.10.4';self.f.states[0]['state']='unavailable';self.f.states[-1]['state']='off'
        self.f.now+=901;s=self.e.observe(s);self.assertEqual(s['state'],'attention_required');self.assertFalse(s['checks']['entities']);self.assertFalse(s['checks']['automations'])
    def test_backup_reuse_requires_same_owner_and_archive(self):
        prior={'state':'completed','ownerScope':O,'backupSlug':'recent','backupVerified':True,'backupArchive':{'sha256':'c'*64}}
        (self.data/'installation-update.json').write_text(json.dumps(prior));self.f.backups=[{'slug':'recent','date':datetime.fromtimestamp(self.f.now-120,timezone.utc).isoformat()}]
        s=self.execute(self.prep('recent'));self.assertEqual(s['state'],'verifying');self.assertTrue(s['backupVerified']);self.assertFalse([x for x in self.f.calls if x[1]=='/backups/new/full'])
    def test_reused_backup_must_contain_the_current_core_version(self):
        prior={'state':'completed','ownerScope':O,'backupSlug':'recent','backupVerified':True,'backupArchive':{'sha256':'c'*64}}
        (self.data/'installation-update.json').write_text(json.dumps(prior));self.f.backups=[{'slug':'recent','date':datetime.fromtimestamp(self.f.now-120,timezone.utc).isoformat()}]
        original=self.f.supervisor
        def altered(path,**kw):
            result=original(path,**kw)
            if path=='/backups/recent/info':result['homeassistant']='2026.6.3'
            return result
        self.e.supervisor=altered
        self.assertEqual(self.execute(self.prep('recent'))['state'],'failed')
    def test_arbitrary_backup_cannot_bypass_capacity(self):
        s=self.execute(self.prep('arbitrary'));self.assertEqual(s['state'],'failed');self.assertFalse([x for x in self.f.calls if x[1]=='/core/update'])
    def test_interrupted_backup_not_repeated(self):
        s=self.prep();s.update(state='backing_up',backupSubmitted=True);self.e.save(s);s=self.e.observe(s);self.assertEqual(s['state'],'backup_uncertain');self.assertFalse([x for x in self.f.calls if x[1]=='/backups/new/full'])
    def test_other_agent_update_is_exclusive(self):
        (self.data/'installation-update.json').write_text(json.dumps({'state':'installing'}))
        with self.assertRaises(RuntimeError):self.prep()
    def test_inspection_does_not_write_or_update(self):
        v=self.e.command({'operation':'inspect','ownerScope':O});self.assertEqual(v['state'],'inspected');self.assertFalse(self.e.path.exists());self.assertFalse([x for x in self.f.calls if x[2].get('method')=='POST'])
    def test_native_backup_read_remains_allowed_during_maintenance(self):
        import agent
        from unittest.mock import Mock
        socket=Mock();socket.recv.side_effect=[json.dumps({'type':'auth_required'}),json.dumps({'type':'auth_ok'}),json.dumps({'id':1234,'type':'result','success':True,'result':{'state':'idle'}})]
        with patch('installation_reset.blocks_mutations',return_value=True),patch.object(agent.websocket,'create_connection',return_value=socket),patch.object(agent.time,'time',return_value=1.234):
            self.assertEqual(agent.home_assistant_ws_command('fixture',{'type':'backup/info'}),{'state':'idle'})
    def test_payload_cannot_request_arbitrary_supervisor_calls(self):
        with self.assertRaises(ValueError):self.e.command({'operation':'inspect','ownerScope':O,'url':'/host/reboot'})
if __name__=='__main__':unittest.main()
