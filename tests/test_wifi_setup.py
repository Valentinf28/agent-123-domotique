import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
import wifi_setup as wifi

INFO={'interfaces':[{'interface':'eth0','type':'ethernet','connected':True,'ipv4':{'address':['192.168.6.80/24']}},{'interface':'wlan0','type':'wireless','connected':False,'ipv4':{'address':[]},'wifi':None}]}
BASE={'operation':'connect','ownerScope':'a'*64,'interface':'wlan0','ssid':'Showroom','password':'private-key-123','operationId':'12345678-1234-1234-1234-123456789abc','confirmed':True}
class WifiTests(unittest.TestCase):
 def setUp(self):wifi._OPERATIONS.clear()
 def test_status_never_returns_password_or_unrelated_interfaces(self):
  info=copy.deepcopy(INFO);info['interfaces'][1]['wifi']={'ssid':'Showroom','psk':'TOPSECRET'}
  result=wifi.command({'operation':'status','ownerScope':'a'*64},Mock(return_value=info))
  self.assertEqual(len(result['interfaces']),1);self.assertNotIn('TOPSECRET',str(result))
 def test_no_adapter_has_truthful_empty_state(self):
  info=copy.deepcopy(INFO);info['interfaces'][1]['wifi']={'ssid':None};self.assertEqual(wifi.snapshot(info)['interfaces'][0]['ssid'],'')
  self.assertEqual(wifi.snapshot({'interfaces':[]})['interfaces'],[])
 def test_scan_deduplicates_and_does_not_expose_bssid(self):
  call=Mock(side_effect=[INFO,{'accesspoints':[{'ssid':'Showroom','signal':30,'auth':'wpa-psk','mac':'PRIVATE'},{'ssid':'Showroom','signal':85,'auth':'wpa-psk'},{'ssid':'Open','signal':99,'auth':'open'}]}])
  result=wifi.command({'operation':'scan','ownerScope':'a'*64,'interface':'wlan0'},call)
  self.assertEqual(len(result['networks']),2);self.assertEqual(result['networks'][1]['signal'],85);self.assertFalse(result['networks'][0]['supported']);self.assertNotIn('PRIVATE',str(result))
 def test_real_supervisor_scan_without_auth_keeps_infrastructure_selectable(self):
  call=Mock(side_effect=[INFO,{'accesspoints':[{'mode':'infrastructure','ssid':'Real Network','frequency':2412,'signal':80,'mac':'PRIVATE'},{'mode':'adhoc','ssid':'Peer','signal':70}]}])
  result=wifi.command({'operation':'scan','ownerScope':'a'*64,'interface':'wlan0'},call)
  self.assertTrue(result['networks'][0]['supported']);self.assertFalse(result['networks'][1]['supported']);self.assertNotIn('PRIVATE',str(result))
 def test_connect_changes_only_wifi_and_dhcp(self):
  call=Mock(side_effect=[INFO,{},INFO]);result=wifi.command(BASE,call)
  args,kw=call.call_args_list[1];self.assertEqual(args[0],'/network/interface/wlan0/update');self.assertEqual(kw['payload']['ipv4'],{'method':'auto'});self.assertEqual(kw['payload']['wifi']['psk'],BASE['password']);self.assertNotIn(BASE['password'],str(result))
 def test_ethernet_required_before_any_write(self):
  info=copy.deepcopy(INFO);info['interfaces'][0]['connected']=False;call=Mock(return_value=info)
  with self.assertRaisesRegex(ValueError,'Ethernet'):wifi.command(BASE,call)
  self.assertEqual(call.call_count,1)
 def test_active_wifi_cannot_be_overwritten(self):
  info=copy.deepcopy(INFO);info['interfaces'][1]['connected']=True;call=Mock(return_value=info)
  with self.assertRaisesRegex(ValueError,'déjà connecté'):wifi.command(BASE,call)
  self.assertEqual(call.call_count,1)
 def test_interface_must_be_a_real_wireless_interface(self):
  call=Mock(return_value=INFO)
  with self.assertRaises(ValueError):wifi.command({**BASE,'interface':'eth0'},call)
  self.assertEqual(call.call_count,1)
 def test_duplicate_operation_is_not_replayed(self):
  call=Mock(return_value=INFO);wifi.command(BASE,call);wifi.command(BASE,call)
  self.assertEqual(sum(c.kwargs.get('method')=='POST' for c in call.call_args_list),1)
 def test_uncertain_failure_is_redacted_and_not_replayed(self):
  call=Mock(side_effect=[INFO,RuntimeError(BASE['password']),INFO])
  with self.assertRaises(RuntimeError) as err:wifi.command(BASE,call)
  self.assertNotIn(BASE['password'],str(err.exception));wifi.command(BASE,call);self.assertEqual(call.call_count,3)
 def test_rejects_injections_missing_consent_and_wrong_scopes(self):
  for changes in [{'interface':'../eth0'},{'ownerScope':'x'},{'confirmed':False},{'operationId':'bad'},{'ssid':'x'*33},{'password':'short'},{'extra':True}]:
   with self.subTest(changes=list(changes)):
    call=Mock()
    with self.assertRaises(ValueError):wifi.command({**BASE,**changes},call)
    call.assert_not_called()
 def test_success_requires_address_and_primary_observed_separately(self):
  info=copy.deepcopy(INFO);info['interfaces'][1].update(connected=True,primary=True,ipv4={'address':['192.168.6.22/24']},wifi={'ssid':'Showroom','psk':'SECRET'});info['interfaces'][0]['connected']=False
  result=wifi.snapshot(info);self.assertFalse(result['ethernetConnected']);self.assertEqual(result['interfaces'][0]['addresses'],['192.168.6.22']);self.assertTrue(result['interfaces'][0]['primary'])
if __name__=='__main__':unittest.main()
