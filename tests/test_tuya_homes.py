import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock
from tuya_homes import read_homes
from tuya_setup import configure

ENTRY={'entryId':'entry1','state':'loaded','disabled':False}
class HomeTests(TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.config=Path(self.temp.name)
  (self.config/'.storage').mkdir()
  (self.config/'.storage/core.config_entries').write_text(json.dumps({'data':{'entries':[{'domain':'tuya','entry_id':'entry1','data':{'secret':'never-export'}},{'domain':'other','entry_id':'other','data':{'secret':'foreign'}}]}}))
 def test_real_membership_separate_from_names_or_rooms(self):
  api=Mock();api.get.side_effect=[{'success':True,'result':[{'ownerId':1,'name':'Maison'},{'ownerId':2,'name':'Maison'}]},{'success':True,'result':[{'id':'devA','local_key':'never-export'}]},{'success':True,'result':[{'id':'devB'}]}]
  factory=Mock(return_value=api);homes,members=read_homes([ENTRY],config=self.config,api_factory=factory)
  self.assertEqual([h['id'] for h in homes],['entry1:1','entry1:2']);self.assertEqual(members[('entry1','devA')],['entry1:1']);self.assertNotIn('never-export',str((homes,members)))
  self.assertEqual(api.get.call_args_list[1].args,('/v1.0/m/life/ha/home/devices',{'homeId':'1'}));api.session.close.assert_called_once()
 def test_failed_home_query_does_not_return_partial_authorization(self):
  api=Mock();api.get.side_effect=[{'success':True,'result':[{'ownerId':1,'name':'One'}]},{'success':False}]
  with self.assertRaises(ValueError):read_homes([ENTRY],config=self.config,api_factory=lambda data:api)
  api.session.close.assert_called_once()
 def test_disabled_entry_never_reads_cloud_or_foreign_credentials(self):
  factory=Mock();self.assertEqual(read_homes([ENTRY|{'disabled':True}],config=self.config,api_factory=factory),([],{}));factory.assert_not_called()
 def test_missing_native_entry_rejected(self):
  with self.assertRaises(ValueError):read_homes([ENTRY|{'entryId':'foreign'}],config=self.config,api_factory=Mock())
 def test_inventory_matches_tuya_identifier_and_config_entry_not_area(self):
  entities=[{'config_entry_id':'entry1','platform':'tuya','entity_id':'switch.one','device_id':'ha1'}]
  devices=[{'id':'ha1','name':'One','area_id':'room1','identifiers':[['tuya','devA']]}]
  registry=Mock(side_effect=[entities,devices,[{'area_id':'room1','name':'Other home'}]])
  call=Mock(side_effect=[[{'domain':'tuya','entry_id':'entry1','state':'loaded','disabled_by':None}],[{'entity_id':'switch.one','state':'on'}]])
  reader=Mock(return_value=([{'id':'entry1:1','name':'Actual home'}],{('entry1','devA'):['entry1:1'],('foreign','devA'):['foreign:2']}))
  result=configure({'operation':'status','ownerScope':'a'*64},call,data=self.config,registry=registry,homes_reader=reader)
  self.assertEqual(result['devices'][0]['homeIds'],['entry1:1']);self.assertEqual(result['homesStatus'],'ready')
 def test_home_failure_is_sanitized_and_fails_closed(self):
  call=Mock(return_value=[{'domain':'tuya','entry_id':'entry1','state':'loaded','disabled_by':None}]);reader=Mock(side_effect=ValueError('secret-token'))
  result=configure({'operation':'status','ownerScope':'a'*64},call,data=self.config,homes_reader=reader)
  self.assertEqual(result['homesStatus'],'unavailable');self.assertEqual(result['homes'],[]);self.assertNotIn('secret-token',json.dumps(result))
if __name__=='__main__':main()
