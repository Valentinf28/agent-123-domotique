import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent_123_domotique'))
spec = importlib.util.spec_from_file_location('hardening_agent', ROOT / 'agent_123_domotique/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class LocalEnergyContract(unittest.TestCase):
    def setUp(self):
        prefix = 'sensor.1_2_3_home_deye_2974839220'
        self.energy = dict(version=1, confirmed=True, scope='site', name='Bâtiment', supply='three',
                           productionMode='devices', production=[prefix+'_pv_power'], grid=['sensor.grid'],
                           gridDirection='import_positive', batteryMode='coupled_dc', battery=[],
                           batteryDirection='discharge_positive', hybrid=[dict(production=prefix+'_pv_power', ac=prefix+'_power')])
        self.document = dict(version=1, agentId='box-fixture', installationId='installation-fixture', revision='a'*64,
                             configuration=dict(electricalSupply='three', houseName='Maison', energyMetering=self.energy, devices={}, automations={}))

    def test_energy_survives_disk_and_republication_without_portal(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(agent, 'LOCAL_CONFIGURATION_PATH', Path(directory)/'configuration.json'):
            self.assertTrue(agent.store_local_configuration(self.document, 'box-fixture'))
            self.assertEqual(json.loads(agent.LOCAL_CONFIGURATION_PATH.read_text()), self.document)
            self.assertFalse(agent.store_local_configuration(self.document, 'box-fixture'))
            with patch.object(agent, 'request_json') as call:
                agent.publish_local_configuration('internal-fixture', 'box-fixture', force=True)
                self.assertEqual(call.call_args.kwargs['payload']['attributes']['configuration']['energyMetering'], self.energy)

    def test_invalid_energy_never_overwrites_last_valid_configuration(self):
        invalids = []
        for change in [dict(version=True), dict(confirmed=False), dict(scope='all'), dict(name=''), dict(supply='single'),
                       dict(grid=['sensor.grid','sensor.other']), dict(production=['sensor.grid']), dict(battery=['sensor.unassigned']),
                       dict(secret='must-not-be-stored'), dict(gridDirection='unknown'), dict(batteryMode='coupled_dc', hybrid=[])]:
            invalids.append({**self.energy, **change})
        invalids.append({**self.energy, 'hybrid':[dict(production=self.energy['production'][0], ac='sensor.foreign_power')]})
        invalids.append({**self.energy, 'production':["sensor.bad'}}{{"]})
        with tempfile.TemporaryDirectory() as directory, patch.object(agent, 'LOCAL_CONFIGURATION_PATH', Path(directory)/'configuration.json'):
            agent.store_local_configuration(self.document, 'box-fixture')
            before=agent.LOCAL_CONFIGURATION_PATH.read_bytes()
            for invalid in invalids:
                document=copy.deepcopy(self.document)
                document['configuration']['energyMetering']=invalid
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    agent.store_local_configuration(document, 'box-fixture')
                self.assertEqual(agent.LOCAL_CONFIGURATION_PATH.read_bytes(), before)

    def test_other_supported_battery_modes(self):
        for mode in ['none','unknown','separate_ac']:
            energy={**self.energy, 'batteryMode':mode, 'hybrid':[], 'production':['sensor.pv'],
                    'battery':['sensor.battery_ac'] if mode=='separate_ac' else []}
            agent.validate_local_energy(energy,'three')


class AuthenticatedTransport(unittest.TestCase):
    def test_external_plaintext_and_url_credentials_rejected_before_network(self):
        for url in ['http://portal.example/api','http://supervisor.evil/core/api', 'http://supervisor:123/api',
                    'https://user:password@portal.example/api','https://portal.example/api#fragment', 'file:///tmp/token', '//portal.example/api']:
            with self.subTest(url=url), patch.object(agent.urllib.request, 'build_opener') as network:
                with self.assertRaises(ValueError):agent.request_json(url,token='fixture')
                network.assert_not_called()
        for url in ['http://supervisor/core/api/states','http://supervisor/addons/self/info','https://home.123panneaux-solaires.fr/api/agent/heartbeat']:
            agent.validate_json_url(url)

    def test_redirect_never_delivers_authorization_or_body_to_other_origin(self):
        received=[]
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):received.append(True);self.send_response(200);self.end_headers();self.wfile.write(b'{}')
            do_POST=do_GET
        target=ThreadingHTTPServer(('127.0.0.1',0),Target)
        class Source(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def redirect(self):
                self.send_response(int(self.path.strip('/')))
                self.send_header('Location',f'http://localhost:{target.server_port}/target')
                self.end_headers()
            do_GET=redirect
            do_POST=redirect
        source=ThreadingHTTPServer(('127.0.0.1',0),Source)
        for server in (source,target):threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            # Bypass only destination validation for these loopback fixtures;
            # the production opener and redirect handler are exercised unchanged.
            with patch.object(agent,'validate_json_url'):
                for code in [301,302,303,307,308]:
                    for method in ['GET','POST']:
                        with self.subTest(code=code,method=method),self.assertRaises((RuntimeError,agent.urllib.error.HTTPError)):
                            agent.request_json(f'http://127.0.0.1:{source.server_port}/{code}',method=method,token='synthetic',payload={'test':'synthetic'} if method=='POST' else None)
            self.assertEqual(received,[])
        finally:
            for server in (source,target):server.shutdown();server.server_close()

    def test_manual_relay_refuses_cleartext(self):
        with patch.object(agent.websocket,'create_connection',create=True) as network:
            with self.assertRaises(ValueError):agent.relay_forever('ws://relay.example','fixture','synthetic','internal')
            network.assert_not_called()


if __name__ == '__main__':unittest.main()
