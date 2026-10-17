import hashlib,json
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import Mock
import yaml
from solar_profile import LP1_PROFILE,LP1_PROFILE_SHA,LEGACY_LP1_PROFILE_SHA
from solar_setup import configure,settings,reconcile_cadence
import test_solar_setup as fixture
from test_solar_setup import ADAPTERS,PAYLOAD

class CadenceTests(TestCase):
 setUp=fixture.SolarSetupTests.setUp
 def source(self):return Path(__file__).parents[1]/'agent_123_domotique/profiles'/LP1_PROFILE
 def previous(self):
  text=self.source().read_text()
  for group in ['Battery','Grid','Load']:text=text.replace('- group: '+group+'\n  update_interval: 5\n', '- group: '+group+'\n')
  self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),LEGACY_LP1_PROFILE_SHA);return text
 def topology(self):return {'loggerSerial':PAYLOAD['loggerSerial'],'mppt':3,'phase':1,'mod':0}
 def migrate_fixture(self):
  root=self.config/'custom_components/solarman';(root/'inverter_definitions/custom'/LP1_PROFILE).write_text(self.previous())
  payload=PAYLOAD|{'model':'deye_lp1'};options=settings(payload,ADAPTERS,self.topology());options.pop('name');entry={'domain':'solarman','entry_id':'saved','options':options};self.storage.write_text(json.dumps({'data':{'entries':[entry]}}));return root,payload
 def test_power_groups_share_five_second_cadence_and_slow_groups_stay_slow(self):
  data=self.source().read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),LP1_PROFILE_SHA);profile=yaml.safe_load(data)
  groups={g['group']:g for g in profile['parameters']}
  for group in ['PV','Battery','Grid','Load']:self.assertEqual(groups[group]['update_interval'],5)
  self.assertEqual(groups['Info']['update_interval'],3600);self.assertEqual(groups['Meter']['update_interval'],30)
  for group in groups.values():
   for item in group['items']:self.assertNotIn(item.get('platform'),['switch','number','select','button'])
 def test_known_legacy_migrates_and_only_selected_entry_reloads_once(self):
  root,payload=self.migrate_fixture();before=self.storage.read_bytes();call=Mock(side_effect=[[{'entry_id':'saved'}],{'require_restart':False}])
  result=configure(payload,ADAPTERS,call,config=self.config,data=self.data,topology_reader=lambda *_:self.topology());self.assertEqual(result['entryId'],'saved');self.assertEqual(call.call_args.args[0],'/config/config_entries/entry/saved/reload');self.assertEqual(self.storage.read_bytes(),before)
  retry=Mock(return_value=[{'entry_id':'saved'}]);configure(payload,ADAPTERS,retry,config=self.config,data=self.data,topology_reader=lambda *_:self.topology());self.assertEqual(retry.call_count,1)
  second=Mock(return_value={'require_restart':False});reconcile_cadence({'entry_id':'other'},root,second,self.data);self.assertEqual(second.call_args.args[0],'/config/config_entries/entry/other/reload')
 def test_unknown_profile_is_preserved_without_reload(self):
  root,payload=self.migrate_fixture();profile=root/'inverter_definitions/custom'/LP1_PROFILE;profile.write_text('client profile');call=Mock()
  with self.assertRaisesRegex(RuntimeError,'conservé'):configure(payload,ADAPTERS,call,config=self.config,data=self.data,topology_reader=lambda *_:self.topology())
  call.assert_not_called();self.assertEqual(profile.read_text(),'client profile')
 def test_failed_reload_is_not_recorded_as_completed_and_can_be_resumed(self):
  root,payload=self.migrate_fixture();call=Mock(side_effect=[[{'entry_id':'saved'}],{'require_restart':True}])
  with self.assertRaises(RuntimeError):configure(payload,ADAPTERS,call,config=self.config,data=self.data,topology_reader=lambda *_:self.topology())
  self.assertFalse((self.data/'solar-cadence-saved.json').exists())
  retry=Mock(side_effect=[[{'entry_id':'saved'}],{'require_restart':False}]);configure(payload,ADAPTERS,retry,config=self.config,data=self.data,topology_reader=lambda *_:self.topology());self.assertEqual(retry.call_count,2)
if __name__=='__main__':main()
