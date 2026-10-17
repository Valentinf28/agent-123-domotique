from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
from ddzy422_setup import install,DOMAIN
from solar_profile import MICRO_PROFILE
from local_solar_measurements import inspect,readiness

NOW=datetime(2026,10,14,14,0,tzinfo=timezone.utc)
class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.config=Path(self.tmp.name);(self.config/'.storage').mkdir();self.storage=self.config/'.storage/core.config_entries';install(self.config)
 def meter(self):
  self.storage.write_text(json.dumps({'data':{'entries':[{'entry_id':'meter','domain':DOMAIN,'data':{'logger_serial':2616442643}}]}}))
  keys={'gridPower':'gridPowerW','importEnergy':'importTotalKwh','exportEnergy':'exportTotalKwh'}
  registry=[{'config_entry_id':'meter','platform':DOMAIN,'entity_id':'sensor.'+role.lower(),'unique_id':f'{DOMAIN}_2616442643_{key}'} for role,key in keys.items()]
  states=[]
  for role,value in [('gridPower',-459),('importEnergy',3083.61),('exportEnergy',5667.90)]:
   energy=role!='gridPower';states.append({'entity_id':'sensor.'+role.lower(),'state':str(value),'last_reported':NOW.isoformat(),'attributes':{'unit_of_measurement':'kWh' if energy else 'W','device_class':'energy' if energy else 'power','state_class':'total_increasing' if energy else 'measurement'}})
  return registry,states
 def test_entry_scoped_meter_negative_grid_and_physical_indexes(self):
  registry,states=self.meter();other={'config_entry_id':'other','platform':DOMAIN,'entity_id':'sensor.other','unique_id':registry[0]['unique_id']}
  call=Mock(side_effect=[[{'entry_id':'meter','state':'loaded'}],states+[{'entity_id':'sensor.other','state':'9999'}]])
  result=inspect('meter','ddzy422',call,registry+[other],config=self.config,now=NOW)
  self.assertTrue(result['readingsAvailable']);self.assertEqual(result['measurements']['gridPower']['value'],-459)
  self.assertEqual(result['entities']['importEnergy'],'sensor.importenergy');self.assertNotIn('sensor.other',call.call_args.kwargs['payload']['template'])
 def test_missing_or_unavailable_state_never_becomes_zero(self):
  registry,states=self.meter();states[0]['state']='unavailable';states.pop()
  result=inspect('meter','ddzy422',Mock(side_effect=[[{'entry_id':'meter','state':'loaded'}],states]),registry,config=self.config,now=NOW)
  self.assertFalse(result['readingsAvailable']);self.assertEqual(result['measurements']['gridPower'],{'status':'unavailable'});self.assertEqual(result['measurements']['exportEnergy'],{'status':'missing'})
 def test_stale_measurements_do_not_validate(self):
  registry,states=self.meter();states[0]['last_reported']=(NOW-timedelta(seconds=91)).isoformat()
  result=inspect('meter','ddzy422',Mock(side_effect=[[{'entry_id':'meter','state':'loaded'}],states]),registry,config=self.config,now=NOW)
  self.assertFalse(result['readingsAvailable']);self.assertEqual(result['measurements']['gridPower']['status'],'stale')
 def test_wrong_model_or_entry_never_reads_other_measurements(self):
  registry,states=self.meter();call=Mock()
  with self.assertRaises(RuntimeError):inspect('meter','deye_micro',call,registry,config=self.config,now=NOW)
  call.assert_not_called()
 def test_micro_uses_only_ac_power_from_verified_profile(self):
  root=self.config/'custom_components/solarman/inverter_definitions/custom';root.mkdir(parents=True)
  shutil.copyfile(Path(__file__).parents[1]/'agent_123_domotique/profiles'/MICRO_PROFILE,root/MICRO_PROFILE)
  self.storage.write_text(json.dumps({'data':{'entries':[{'entry_id':'micro','domain':'solarman','options':{'logger_serial':3840836493,'lookup_file':'custom/'+MICRO_PROFILE}}]}}))
  registry=[{'config_entry_id':'micro','platform':'solarman','entity_id':'sensor.micro_ac','original_name':'Power'}, {'config_entry_id':'micro','platform':'solarman','entity_id':'sensor.micro_dc','original_name':'PV Power'}]
  state={'entity_id':'sensor.micro_ac','state':'0.5937','last_reported':NOW.isoformat(),'attributes':{'unit_of_measurement':'kW','device_class':'power'}}
  call=Mock(side_effect=[[{'entry_id':'micro','state':'loaded'}],[state]])
  result=inspect('micro','deye_micro',call,registry,config=self.config,now=NOW)
  self.assertTrue(result['readingsAvailable']);self.assertAlmostEqual(result['measurements']['production']['value'],593.7)
  self.assertEqual(result['entities'],{'production':'sensor.micro_ac'});self.assertNotIn('sensor.micro_dc',call.call_args.kwargs['payload']['template'])
 def test_readiness_is_readonly_and_requires_native_correct_versions(self):
  call=Mock(return_value=['solarman',DOMAIN]);manifest=lambda domain:{'domain':domain,'is_built_in':False,'version':'25.08.16+labox.1' if domain=='solarman' else '0.1.1'}
  self.assertEqual(readiness(call,manifest),{'solarmanReady':True,'ddzyReady':True});self.assertEqual(call.call_count,1)
  self.assertEqual(readiness(call,lambda domain:{'domain':domain,'is_built_in':True,'version':'wrong'}),{'solarmanReady':False,'ddzyReady':False})

if __name__=='__main__':unittest.main()
