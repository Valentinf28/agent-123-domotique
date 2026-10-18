import importlib.util
from pathlib import Path
import sys, types, unittest
sys.modules.setdefault('websocket', types.ModuleType('websocket'))
spec=importlib.util.spec_from_file_location('tahoma_agent',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)

class TahomaMetadataTests(unittest.TestCase):
 def test_imports_native_room_and_exact_low_speed_identity_without_exposing_urls(self):
  rows=[{'entity_id':'cover.one','platform':'overkiz','device_id':'device','unique_id':'io://private-gateway/motor'},
        {'entity_id':'cover.one_slow','platform':'overkiz','device_id':'device','unique_id':'io://private-gateway/motor_low_speed'}]
  devices=[{'id':'device','area_id':'kitchen','name':'Porte fenêtre cuisine','configuration_url':'https://private','identifiers':[['overkiz','io://private-gateway/motor']]}]
  result=agent.registry_metadata_from_results(rows,devices,[{'area_id':'kitchen','name':'Cuisine'}])
  self.assertEqual(result['cover.one']['area_name'],'Cuisine')
  self.assertEqual(result['cover.one']['device_name'],'Porte fenêtre cuisine')
  self.assertEqual(result['cover.one_slow']['overkiz_primary_entity'],'cover.one')
  self.assertNotIn('private',str(result))
 def test_entity_room_precedes_device_room_and_other_motors_do_not_merge(self):
  rows=[{'entity_id':'cover.one','platform':'overkiz','device_id':'first','unique_id':'motor'},
        {'entity_id':'cover.two','platform':'overkiz','device_id':'second','unique_id':'motor_low_speed','area_id':'bath'}]
  result=agent.registry_metadata_from_results(rows,[{'id':'second','area_id':'kitchen'}],[{'area_id':'kitchen','name':'Cuisine'},{'area_id':'bath','name':'Salle de bain'}])
  self.assertEqual(result['cover.two']['area_name'],'Salle de bain')
  self.assertNotIn('overkiz_primary_entity',result['cover.two'])
 def test_no_room_is_invented_and_missing_areas_keep_device_information(self):
  result=agent.registry_metadata_from_results([{'entity_id':'cover.one','platform':'overkiz','device_id':'first'}],[{'id':'first','name':'Salon'}])
  self.assertNotIn('area_name',result['cover.one'])
  self.assertEqual(result['cover.one']['device_name'],'Salon')
