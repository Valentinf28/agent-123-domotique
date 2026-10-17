import http.client
import ipaddress
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from shelly_lan import identify, scan, start
from shelly_setup import configure
from test_shelly_setup import Native, OWNER, SESSION, MAC

LAN={'flowId':'lan_'+MAC,'domain':'shelly','mac':MAC,'name':'shellyplus1-'+MAC,'step':'confirm_discovery','host':'192.168.9.22'}
class LanNative(Native):
 def __init__(self,protected=False,selection=False):
  super().__init__();self.source='bluetooth';self.step='bluetooth_confirm';self.protected=protected;self.selection=selection;self.hosted=False;self.calls=[]
 def call(self,path,**kwargs):
  self.calls.append((path,kwargs))
  if path=='/config/config_entries/flow':
   self.assert_payload=kwargs['payload']
   return {'type':'form','handler':'shelly','flow_id':'manual1','step_id':'user','data_schema':[{'name':'device','selector':{'select':{'options':[{'value':'manual','label':'manual'}]}}}] if self.selection else [{'name':'host'},{'name':'port'},{'name':'verify_ssl'}]}
  if path=='/config/config_entries/flow/manual1':
   payload=kwargs.get('payload')
   if payload=={'device':'manual'}:
    return {'type':'form','handler':'shelly','flow_id':'manual1','step_id':'user_manual','data_schema':[{'name':'host'},{'name':'port'},{'name':'verify_ssl'}]}
   if payload and 'host' in payload:self.hosted=True
   if self.protected and not payload or self.protected and 'password' not in (payload or {}):
    return {'type':'form','handler':'shelly','flow_id':'manual1','step_id':'credentials','data_schema':[{'name':'password'}]}
   self.native=[{'entry_id':'entry1','domain':'shelly','state':'loaded','disabled_by':None}]
   self.device_rows=[{'id':'device1','config_entries':['entry1'],'manufacturer':'Shelly','model':'Plus 1','connections':[['mac',MAC]]}]
   return {'type':'create_entry','result':{'entry_id':'entry1','unique_id':MAC}}
  return super().call(path,**kwargs)

class LanTests(TestCase):
 def setUp(self):self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.data=Path(self.temp.name)
 def step(self,n,operation='status',identifier=None,**extra):
  payload={'operation':operation,'ownerScope':OWNER}
  if operation!='status':payload.update(session=SESSION,flowId=LAN['flowId'],mac=MAC)
  return configure(payload|extra,n.call,registry=n.registry,data=self.data,lan=lambda:[dict(LAN)],identify=identifier or (lambda host:dict(LAN)),clock=lambda:100)
 def test_ble_wifi_candidate_becomes_readonly_lan_discovery(self):
  n=LanNative();r=self.step(n);self.assertEqual(r['discoveries'],[{k:LAN[k] for k in ('flowId','domain','mac','name','step')}]);self.assertFalse(any(k.get('method')=='POST' for _,k in n.calls));self.assertNotIn('host',r['discoveries'][0])
 def test_both_native_manual_forms_use_only_host_without_ble_provisioning(self):
  for selection in (False,True):
   with TemporaryDirectory() as temp:
    self.data=Path(temp);n=LanNative(selection=selection);r=self.step(n,'connect',confirmed=True)
    self.assertEqual(len(r['devices']),1);self.assertEqual(r['discoveries'],[])
    self.assertTrue(n.hosted);self.assertEqual([k['payload'] for p,k in n.calls if k.get('payload',{}).get('host')],[{'host':LAN['host'],'port':80,'verify_ssl':True}])
    self.assertFalse(any(p.endswith('/flow1') for p,_ in n.calls))
 def test_dhcp_identity_change_stops_before_any_flow(self):
  n=LanNative()
  with self.assertRaises(RuntimeError):self.step(n,'connect',identifier=lambda host:{'mac':'112233445566'},confirmed=True)
  self.assertFalse(any(k.get('method')=='POST' for _,k in n.calls))
 def test_identity_is_rechecked_before_host_submission(self):
  n=LanNative();checks=iter([dict(LAN),{'mac':'112233445566'}])
  with self.assertRaises(RuntimeError):self.step(n,'connect',identifier=lambda host:next(checks),confirmed=True)
  self.assertFalse(n.hosted)
 def test_password_retry_resume_is_owned_and_secret_not_persisted(self):
  n=LanNative(protected=True);r=self.step(n,'connect',confirmed=True);self.assertEqual(r['authentication']['flowId'],LAN['flowId']);self.assertEqual(r['discoveries'][0]['step'],'credentials')
  before=len(n.calls)
  with self.assertRaises(RuntimeError):self.step(n,'credentials',ownerScope='b'*64,username='',password='private-secret')
  self.assertFalse(any(k.get('method')=='POST' for _,k in n.calls[before:]))
  r=self.step(n,'credentials',username='',password='private-secret');self.assertEqual(len(r['devices']),1);self.assertNotIn('private-secret',json.dumps(r));self.assertNotIn('private-secret',(self.data/'shelly-setup.json').read_text())
 def test_lost_create_reply_reconciles_without_duplicate_entry(self):
  n=LanNative();self.step(n,'connect',confirmed=True);before=len(n.calls);self.step(n,'connect',confirmed=True);self.assertFalse(any(k.get('method')=='POST' for _,k in n.calls[before:]))
 def test_lan_probe_rejects_external_localhost_box_and_redirect(self):
  interfaces=[ipaddress.IPv4Interface('192.168.9.5/24')]
  with patch('shelly_lan.http.client.HTTPConnection') as factory:
   for host in ('8.8.8.8','127.0.0.1','169.254.169.254','192.168.9.5','192.168.9.0','192.168.9.255','192.168.10.4'):
    with self.assertRaises(ValueError):identify(host,interfaces)
   factory.assert_not_called();factory.return_value.getresponse.return_value.status=302
   with self.assertRaises(ValueError):identify('192.168.9.22',interfaces)
   factory.return_value.request.assert_called_once_with('GET','/shelly',headers={'Accept':'application/json'})
 def test_probe_requires_shelly_model_and_matching_mac_id(self):
  interfaces=[ipaddress.IPv4Interface('192.168.9.5/24')]
  with patch('shelly_lan.http.client.HTTPConnection') as factory:
   response=factory.return_value.getresponse.return_value;response.status=200
   for info in ({'mac':MAC},{'mac':MAC,'gen':2,'id':'other-'+MAC,'model':'Other'},{'mac':'010000000001','type':'SHSW-1'}):
    response.read.return_value=json.dumps(info).encode()
    with self.assertRaises(ValueError):identify(LAN['host'],interfaces)
   response.read.return_value=json.dumps({'mac':MAC.upper(),'gen':2,'id':'shellyplus1-'+MAC,'model':'SNSW-001X16EU'}).encode()
   self.assertEqual(identify(LAN['host'],interfaces)['mac'],MAC)
 def test_scan_is_bounded_cached_and_ambiguous_identity_not_offered(self):
  adapters=[{'enabled':True,'ipv4':[{'address':'192.168.9.5','network_prefix':24}]}];seen=[]
  def probe(host,interfaces):seen.append(host);return dict(LAN,host=host) if host in ('192.168.9.22','192.168.9.23') else None
  with patch('shelly_lan.current_adapters',return_value=adapters):
   self.assertEqual(scan(adapters,probe=probe,clock=lambda:1000),[]);self.assertEqual(len(seen),253)
   scan(adapters,probe=probe,clock=lambda:1001);self.assertEqual(len(seen),253)
if __name__=='__main__':main()
