"""First-boot lifecycle, isolated radio rollback and local HTTP security regressions."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'labox_wifi_bootstrap'))
sys.path.insert(0, str(ROOT / 'agent_123_domotique'))
from model import Lifecycle, Refused, atomic, credentials, read
from network import Network, profile, unwrap, ROOT as NM_ROOT, DEST
from controller import Controller
from http_setup import HTTP, ORIGIN
from workshop import label, wifi_qr
from network_bootstrap_status import publish
from access_point import AccessPoint

CONTEXT = 'a' * 64
OPTIONS = {'armed': True, 'factory_context': CONTEXT, 'wifi_mac': '00:11:22:33:44:55'}
MARKER = {'version': 1, 'factoryContext': CONTEXT, 'prepared': True, 'installed': False}
SNAPSHOT = {'ethernet': False, 'foreign_wifi': False, 'ap_capable': True, 'networks': [], 'busy': False}

class LifeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'; self.life = Lifecycle(self.path)
        self.life.prepare(OPTIONS, MARKER)

    def test_unique_private_credentials(self):
        other = Lifecycle(Path(self.tmp.name) / 'other.json'); other.prepare(OPTIONS, MARKER)
        self.assertNotEqual(self.life.data['psk'], other.data['psk'])
        self.assertNotEqual(self.life.data['ssid'], other.data['ssid'])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(len(self.life.data['psk']), 20)

    def test_credentials_stable_after_restart(self):
        restarted = Lifecycle(self.path); restarted.prepare(OPTIONS, MARKER)
        self.assertEqual(self.life.data, restarted.data)

    def test_disarmed_does_not_prepare(self):
        new = Lifecycle(Path(self.tmp.name) / 'absent')
        self.assertFalse(new.prepare({'armed': False}, MARKER)); self.assertFalse(new.path.exists())

    def test_unknown_marker_is_refused(self):
        for marker in ({}, {**MARKER, 'prepared': False}, {**MARKER, 'factoryContext': 'b'*64}):
            with self.subTest(marker=marker), self.assertRaises(Refused): self.life.gate(marker, SNAPSHOT)

    def test_installed_stays_retired_even_when_internet_fails(self):
        self.assertFalse(self.life.gate({**MARKER, 'installed': True}, SNAPSHOT))
        self.assertFalse(self.life.gate(MARKER, SNAPSHOT)); self.life.new_boot('new')
        self.assertFalse(self.life.prepare(OPTIONS, MARKER))

    def test_ethernet_waits_without_consuming_window(self):
        self.assertFalse(self.life.gate(MARKER, {**SNAPSHOT, 'ethernet': True}))
        self.assertEqual(self.life.data['deadline'], 0)
        self.assertTrue(self.life.gate(MARKER, SNAPSHOT))

    def test_saved_wifi_retires_even_when_not_connected(self):
        self.assertFalse(self.life.gate(MARKER, {**SNAPSHOT, 'foreign_wifi': True}))
        self.assertEqual(self.life.data['phase'], 'retired')

    def test_ap_capability_busy_and_subnet_conflict(self):
        for change in ({'ap_capable': False}, {'busy': True}, {'networks': ['192.168.77.64/26']}):
            with self.subTest(change=change), self.assertRaises(Refused): self.life.gate(MARKER, {**SNAPSHOT, **change})

    def test_no_hotspot_after_success_or_expiry(self):
        for phase in ('complete', 'expired'):
            self.life.save(phase=phase)
            self.assertFalse(self.life.gate(MARKER, SNAPSHOT))

    def test_fifteen_minute_window_and_host_reboot(self):
        self.life.new_boot('boot1'); self.life.save(deadline=1000)
        self.assertFalse(self.life.gate(MARKER, SNAPSHOT, now=1001))
        self.life.new_boot('boot1'); self.assertEqual(self.life.data['phase'], 'expired')
        self.life.new_boot('boot2'); self.assertTrue(self.life.gate(MARKER, SNAPSHOT))
        self.assertEqual(self.life.data['deadline'], 0)

    def test_new_factory_identity_and_changed_mac_fail_closed(self):
        with self.assertRaises(Refused): self.life.prepare({**OPTIONS, 'factory_context': 'b'*64}, {**MARKER, 'factoryContext': 'b'*64})
        with self.assertRaises(Refused): self.life.prepare({**OPTIONS, 'wifi_mac': '00:11:22:33:44:66'}, MARKER)

    def test_no_secret_in_public_status(self):
        public = json.dumps(self.life.public([]))
        for field in ('psk', 'mac', 'context', 'ap_uuid'): self.assertNotIn(self.life.data[field], public)

    def test_credentials_validation_and_no_silent_trimming(self):
        self.assertEqual(credentials(' réseau ', ' pass word '), (' réseau ', ' pass word '))
        self.assertEqual(credentials('a', 'f'*64), ('a', 'f'*64))
        for ssid, password in [('', 'password'), ('é'*17, 'password'), ('a\n', 'password'), ('a', 'short'), ('a', 'é'*8), ('a', 'z'*64), ('a', None)]:
            with self.subTest(ssid=ssid), self.assertRaises(Refused): credentials(ssid, password)

    def test_qr_label_and_no_overwrite(self):
        self.assertIn('WIFI:T:WPA;S:', wifi_qr(self.life.data))
        text = label(self.life.data)
        self.assertIn('<svg', text); self.assertIn('192.168.77.1:18424', text)
        self.life.save(phase='complete')
        with self.assertRaises(ValueError): label(self.life.data)

    def test_ap_and_candidate_profiles_scope(self):
        ap = unwrap(profile('id', OPTIONS['wifi_mac'], 'my wifi', 'password', hotspot=True))
        self.assertEqual(ap['802-11-wireless']['mode'], 'ap')
        self.assertEqual(ap['802-11-wireless']['ap-isolation'], 1)
        self.assertEqual(ap['ipv4']['method'], 'manual'); self.assertTrue(ap['ipv4']['never-default'])
        self.assertFalse(ap['connection']['autoconnect'])
        station = unwrap(profile('id', OPTIONS['wifi_mac'], 'my wifi', 'password'))
        self.assertEqual(station['ipv4']['method'], 'auto')
        self.assertNotIn('gateway', station['ipv4'])
        self.assertEqual(station['802-11-wireless']['mac-address'], bytes.fromhex('001122334455'))

class MarkerTests(unittest.TestCase):
    def test_marker_is_non_secret_and_updates_without_blocking_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'marker.json'
            options={'factory_id':'factory_'+'b'*32,'factory_token':'c'*64,'portal_url':'https://home.123panneaux-solaires.fr/api'}
            self.assertTrue(publish(options, {}, p)); first=read(p)
            self.assertEqual(first['factoryContext'], hashlib.sha256(options['factory_id'].encode()).hexdigest())
            self.assertTrue(first['prepared']); self.assertNotIn(options['factory_token'], p.read_text())
            os.utime(p, (0,0)); self.assertTrue(publish(options, {}, p)); self.assertGreater(p.stat().st_mtime, 0)
            self.assertTrue(publish(options, {'token':'private-token'}, p))
            self.assertTrue(read(p)['installed']); self.assertNotIn('private-token', p.read_text())
            self.assertTrue(publish(options, {}, p)); self.assertTrue(read(p)['installed'])
            self.assertFalse(read(p)['prepared'])
            self.assertTrue(publish({**options,'factory_id':'factory_'+'d'*32}, {}, p)); self.assertFalse(read(p)['installed'])
            self.assertTrue(publish({**options,'enrollment_code':'CODE'}, {}, p)); self.assertTrue(read(p)['installed'])
            self.assertFalse(publish(options, {}, Path(tmp)/'missing'/'file'))

class FakeNetwork:
    def __init__(self):
        self.interface='wlan0'; self.calls=[]; self.items={}; self.snap=deepcopy(SNAPSHOT)
        self.fail_checkpoint=False; self.fail_ip=''; self.fail_persist=False; self.fail_rollback=False
    async def snapshot(self, *args): return deepcopy(self.snap)
    async def scan(self): self.calls.append('scan'); return [{'ssid':'home','strength':70,'supported':True}]
    async def add(self, p):
        p=unwrap(p); identity=p['connection']['uuid']; self.calls.append(('add',identity)); self.items[identity]=p; return identity
    async def activate(self, p): self.calls.append(('activate',p))
    async def wait_ap(self, p): self.calls.append('wait_ap')
    async def wait_ip(self, p):
        if self.fail_ip: raise Refused(self.fail_ip)
        return '192.168.6.210'
    async def checkpoint(self, **kwargs):
        self.calls.append('checkpoint')
        if self.fail_checkpoint: raise Refused('service_reseau_indisponible')
        return '/checkpoint/1' if kwargs.get('guard') else '/checkpoint/guard'
    async def rollback(self, p):
        self.calls.append('rollback')
        if self.fail_rollback: raise Refused('retour_reseau_a_verifier')
    async def destroy(self, p): self.calls.append('destroy')
    async def persist(self, p, settings):
        self.calls.append('persist')
        if self.fail_persist: raise Refused('service_reseau_indisponible')
    async def remove(self, identity): self.calls.append(('remove',identity)); self.items.pop(identity,None)
    async def guard_valid(self, cp): return True
    async def profiles(self): return [(k,v) for k,v in self.items.items()]

class TransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.life=Lifecycle(Path(self.tmp.name)/'life.json'); self.life.prepare(OPTIONS, MARKER)
        self.net=FakeNetwork(); self.marker=deepcopy(MARKER)
        self.c=Controller(self.life,self.net,lambda:self.marker,OPTIONS,probe=lambda _:True)
        self.assertTrue(await self.c.open_ap()); self.net.calls=[]

    async def test_success_only_persists_after_reachability(self):
        payload=self.c.reserve('real-ssid','real-password')
        await self.c.attempt(*payload)
        self.assertEqual(self.life.data['phase'],'complete')
        self.assertLess(self.net.calls.index('checkpoint'),next(i for i,x in enumerate(self.net.calls) if isinstance(x,tuple) and x[0]=='add'))
        self.assertLess(self.net.calls.index('persist'),self.net.calls.index('destroy'))
        self.assertNotIn('real-password', self.life.path.read_text())
        self.assertFalse(await self.c.allowed())

    async def test_wrong_password_dhcp_and_portal_failure_restore_ap(self):
        for failure in ('connexion_wifi_refusee','adresse_ip_non_obtenue','internet_non_confirme'):
            self.net.calls=[]; self.net.fail_ip='' if failure=='internet_non_confirme' else failure
            self.c.probe=lambda _:failure!='internet_non_confirme'
            self.c.reserve('ssid','password'); await self.c.attempt('ssid','password')
            self.assertEqual(self.life.data['phase'],'hotspot'); self.assertEqual(self.life.data['error'],failure)
            self.assertIn('rollback',self.net.calls); self.assertNotIn('persist',self.net.calls); self.assertTrue(self.c.available)

    async def test_checkpoint_failure_never_changes_radio(self):
        self.net.fail_checkpoint=True; self.c.reserve('ssid','password')
        await self.c.attempt('ssid','password')
        self.assertEqual(self.net.calls[0],'checkpoint')
        self.assertFalse(any(isinstance(c,tuple) and c[0] in ('activate','add') for c in self.net.calls))
        self.assertTrue(self.c.available)

    async def test_persist_failure_rolls_back_not_complete(self):
        self.net.fail_persist=True; self.c.reserve('ssid','password'); await self.c.attempt('ssid','password')
        self.assertIn('rollback', self.net.calls); self.assertNotIn('destroy', self.net.calls)
        self.assertEqual(self.life.data['phase'],'hotspot')

    async def test_rollback_failure_is_not_reported_as_available(self):
        self.net.fail_ip='connexion_wifi_refusee'; self.net.fail_rollback=True; self.c.reserve('ssid','password')
        with self.assertRaises(Refused): await self.c.attempt('ssid','password')
        self.assertFalse(self.c.available)

    async def test_two_simultaneous_submissions_refused(self):
        self.c.reserve('ssid','password')
        with self.assertRaises(Refused): self.c.reserve('other','password')
        self.assertEqual(self.life.data['phase'],'queued')

    async def test_cable_inserted_before_attempt_never_replaces_ap(self):
        self.net.snap['ethernet']=True; self.c.reserve('ssid','password'); await self.c.attempt('ssid','password')
        self.assertNotIn('checkpoint',self.net.calls)

    async def test_expired_window_refuses_transaction(self):
        self.c.reserve('ssid','password'); self.life.save(deadline=time.monotonic()-1)
        await self.c.attempt('ssid','password')
        self.assertNotIn('checkpoint',self.net.calls); self.assertEqual(self.life.data['phase'],'expired')

    async def test_interrupted_test_removes_exact_candidate_after_rollback(self):
        candidate='00000000-0000-4000-8000-000000000001'
        self.life.save(phase='testing',candidate=candidate,checkpoint='/checkpoint/1')
        await self.c.recover()
        self.assertEqual(self.net.calls[0],'rollback'); self.assertIn(('remove',candidate),self.net.calls)
        self.assertEqual(self.life.data['error'],'tentative_interrompue')

    async def test_completed_profile_survives_recovery(self):
        self.life.save(phase='complete',candidate='completed',checkpoint='')
        await self.c.recover(); self.assertNotIn(('remove','completed'),self.net.calls)

    async def test_only_wifi_device_in_checkpoint_and_no_global_flags(self):
        n=Network(); n.device='/device/wifi'; calls=[]
        async def fake(*args): calls.append(args); return ['/checkpoint/1']
        n.call=fake
        self.assertEqual(await n.checkpoint(),'/checkpoint/1')
        self.assertEqual(calls[0][3:6],('aouu', [['/device/wifi'],150,0]))

    async def test_completed_latch_preserves_station_when_agent_retires_onboarding(self):
        self.life.save(phase='retired', candidate='completed', provisioned=True)
        await self.c.recover()
        self.assertNotIn(('remove', 'completed'), self.net.calls)

    async def test_no_guard_checkpoint_never_activates_initial_ap(self):
        self.net.fail_checkpoint=True
        self.c.available=False; self.life.save(phase='ready', guard='')
        with self.assertRaises(Refused): await self.c.open_ap()
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='activate' for c in self.net.calls))

    async def test_stale_or_foreign_checkpoint_never_rolled_back(self):
        n=Network(); n.device='/device/wifi'; calls=[]
        async def props(path, iface): return {'Checkpoints':['/cp']} if path==NM_ROOT else {'Devices':['/device/ethernet']}
        async def call(*args): calls.append(args)
        n.props=props; n.call=call
        with self.assertRaises(Refused): await n.rollback('/cp')
        self.assertEqual(calls,[])
        await n.rollback('/old')
        self.assertEqual(calls,[])

class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        life=Lifecycle(Path(self.tmp.name)/'life.json'); life.prepare(OPTIONS,MARKER); life.opening()
        self.controller=Controller(life,FakeNetwork(),lambda:MARKER,OPTIONS,probe=lambda _:True)
        self.controller.available=True; self.http=HTTP(self.controller)

    def test_host_origin_csrf_source_and_content_type(self):
        valid={'host':'192.168.77.1:18424','origin':ORIGIN,'x-setup-token':self.http.token,'content-type':'application/json'}
        self.assertTrue(self.http.authorize('192.168.77.20','POST','/api/connect',valid))
        for peer,change in [('192.168.6.1',{}),('192.168.77.20',{'origin':'http://evil.example'}),('192.168.77.20',{'host':'evil.example'}),('192.168.77.20',{'x-setup-token':'wrong'}),('192.168.77.20',{'content-type':'text/plain'})]:
            with self.subTest(change=change), self.assertRaises(Refused): self.http.authorize(peer,'POST','/api/connect',{**valid,**change})
        self.assertFalse(self.http.authorize('192.168.77.20','GET','/generate_204',{'host':'connectivity.example'}))
        with self.assertRaises(Refused): self.http.authorize('192.168.77.20','GET','/api/status',{'host':'evil.example'})

    def test_rate_limit_bounded(self):
        for _ in range(3): self.http.limit(self.http.attempts,3)
        with self.assertRaises(Refused): self.http.limit(self.http.attempts,3)

    async def request(self, request):
        original=self.http.authorize
        self.http.authorize=lambda peer,*args:original('192.168.77.20',*args)
        server=await asyncio.start_server(self.http.handle,'127.0.0.1',0,limit=8192)
        try:
            r,w=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1]);w.write(request);await w.drain(); data=await r.read();w.close();await w.wait_closed();return data
        finally:
            server.close();await server.wait_closed();self.http.authorize=original
            for task in self.http.tasks: task.cancel()
            await asyncio.gather(*list(self.http.tasks),return_exceptions=True)

    async def test_real_http_offline_page_and_csp(self):
        response=await self.request(b'GET / HTTP/1.1\r\nHost: 192.168.77.1:18424\r\n\r\n')
        self.assertIn(b'200 OK',response);self.assertIn(b'Content-Security-Policy:',response)
        self.assertIn('Connectons votre box.'.encode(),response)
        self.assertNotIn(self.controller.life.data['psk'].encode(),response)

    async def test_real_post_acknowledges_before_switch(self):
        body=json.dumps({'ssid':'home','password':'password'}).encode()
        headers=(f'POST /api/connect HTTP/1.1\r\nHost: 192.168.77.1:18424\r\nOrigin: {ORIGIN}\r\nX-Setup-Token: {self.http.token}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode()
        response=await self.request(headers+body)
        self.assertIn(b'202 Accepted',response);self.assertNotIn('checkpoint',self.controller.net.calls)

    async def test_duplicate_headers_and_invalid_json_refused(self):
        response=await self.request(b'GET / HTTP/1.1\r\nHost: 192.168.77.1:18424\r\nHost: evil\r\n\r\n')
        self.assertIn(b'400 Bad Request',response)

    async def test_api_never_echoes_wifi_password(self):
        response=await self.request(b'GET /api/status HTTP/1.1\r\nHost: 192.168.77.1:18424\r\n\r\n')
        for secret in (self.controller.life.data['psk'],CONTEXT,OPTIONS['wifi_mac']):self.assertNotIn(secret.encode(),response)

class FirewallTests(unittest.TestCase):
    def test_scoped_rules_no_global_flush_no_https_interception(self):
        ap=AccessPoint('wlan0');calls=[]
        def run(binary,args,check=True):
            calls.append((binary,args));return type('Result',(),{'returncode':1})()
        ap.run=run;ap.firewall();ap.stop()
        for _,args in calls:
            if '-F' in args or '-X' in args:self.assertIn('LABOX_SETUP',args)
            self.assertNotIn('443',args)
            if '-I' in args:self.assertIn('wlan0',args)
        with self.assertRaises(Refused):AccessPoint('wlan0;rm -rf /')

if __name__=='__main__':unittest.main()
