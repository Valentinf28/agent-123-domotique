import sys,json,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from network_discovery import current_adapters,local_interfaces
class LiveAddressTests(unittest.TestCase):
 def test_dhcp_change_replaces_stale_ha_address(self):
  old=[{'enabled':True,'ipv4':[{'address':'192.168.6.179','network_prefix':24}]}]
  rows=[{'ifname':'end0','addr_info':[{'family':'inet','local':'192.168.6.180','prefixlen':24}]},{'ifname':'docker0','addr_info':[{'family':'inet','local':'172.17.0.1','prefixlen':16}]}]
  with patch('network_discovery.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(rows))):
   found=local_interfaces(current_adapters(old))
  self.assertEqual([str(i.ip) for i in found],['192.168.6.180'])
 def test_unavailable_os_query_keeps_fallback(self):
  old=[{'enabled':True,'ipv4':[]}]
  for error in (FileNotFoundError(),subprocess.TimeoutExpired('ip',3)):
   with patch('network_discovery.subprocess.run',side_effect=error):self.assertEqual(current_adapters(old),old)
