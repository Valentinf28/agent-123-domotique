import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from solar_recovery import replacement
A=[{'enabled':True,'ipv4':[{'address':'192.168.6.179','network_prefix':24}]}]
O={'host':'192.168.6.178','logger_serial':2974839220}
D={'host':'192.168.6.90','loggerSerial':2974839220,'mac':'d4:27:87:14:07:16','connector':'solarman','status':'found'}
class RecoveryTests(unittest.TestCase):
 def test_changed_address_same_identity(self):self.assertEqual(replacement(O,[D],A),'192.168.6.90')
 def test_wrong_logger(self):self.assertIsNone(replacement(O,[dict(D,loggerSerial=2613499005)],A))
 def test_ambiguous(self):
  self.assertIsNone(replacement(O,[D,dict(D,host='192.168.6.91')],A))
  self.assertIsNone(replacement(O,[dict(D,status='ambiguous')],A))
 def test_unknown_port_is_not_identity(self):self.assertIsNone(replacement(O,[{'host':'192.168.6.90','port':8899}],A))
 def test_remote_or_own_address(self):
  for host in ['8.8.8.8','192.168.7.90','192.168.6.179','192.168.6.255']:
   self.assertIsNone(replacement(O,[dict(D,host=host)],A))
 def test_unchanged(self):self.assertIsNone(replacement(O,[dict(D,host=O['host'])],A))

class RecoveryFlowTests(unittest.TestCase):
 def test_updates_only_host_through_options_flow(self):
  import tempfile,json
  from unittest.mock import Mock
  from solar_recovery import recover
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'custom_components/solarman').mkdir(parents=True);(root/'.storage').mkdir()
   (root/'custom_components/solarman/123home-bundle.json').write_text('{}')
   options={**O,'lookup_file':'custom/deye_sg01hp3_readonly.yaml','additional_options':{'mod':1}}
   (root/'.storage/core.config_entries').write_text(json.dumps({'data':{'entries':[{'domain':'solarman','entry_id':'entry','options':options}]}}))
   call=Mock(side_effect=[[{'entity_id':'sensor.battery','state':'unavailable','last_changed':'2020-01-01T00:00:00Z'}],{'type':'form','step_id':'init','flow_id':'flow'},{'type':'create_entry'}])
   ws=Mock(side_effect=[{'result':[{'entity_id':'sensor.battery','config_entry_id':'entry'}]},{'adapters':A}])
   self.assertEqual(recover(call,ws,config=root,discover=lambda _: {'devices':[D]}),[{'entryId':'entry','host':D['host']}])
   self.assertEqual(call.call_args.kwargs['payload'],{**options,'host':D['host']})
   self.assertEqual(json.loads((root/'.storage/core.config_entries').read_text())['data']['entries'][0]['options'],options)
