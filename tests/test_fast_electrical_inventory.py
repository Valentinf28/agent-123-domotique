import importlib.util,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.modules.setdefault('websocket',types.ModuleType('websocket'))
spec=importlib.util.spec_from_file_location('agent_fast_electrical',Path(__file__).parents[1]/'agent_123_domotique/agent.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
class FastElectricalTests(unittest.TestCase):
 def test_arbitrarily_named_electrical_sensors_are_in_every_fast_summary(self):
  rows=[{'entity_id':'sensor.renamed_'+kind,'state':'12','attributes':{'device_class':kind,'unit_of_measurement':'W'}} for kind in ['power','energy','current','voltage','frequency','power_factor']]
  rows.append({'entity_id':'sensor.private_temperature','state':'21','attributes':{'device_class':'temperature'}})
  with patch.object(agent,'request_json',side_effect=[{},rows,[]]),patch.object(agent,'maintain_daily_pv_peak'),patch.object(agent,'home_assistant_registry_metadata') as registry:
   result=agent.home_assistant_summary('fixture',full_inventory=False)
  registry.assert_not_called();self.assertEqual({x['entityId'] for x in result['inventory']},{x['entity_id'] for x in rows[:-1]})
 def test_energy_state_class_survives_full_and_delta_but_unknown_metadata_is_dropped(self):
  from contextlib import ExitStack
  rows=[{'entity_id':'sensor.energy_'+str(i),'state':'123.45','attributes':{'device_class':'energy','unit_of_measurement':'kWh','state_class':kind,'private_token':'never-export'}} for i,kind in enumerate(['total_increasing','total','measurement','arbitrary-secret',None])]
  for full in (True,False):
   with ExitStack() as stack:
    stack.enter_context(patch.object(agent,'request_json',side_effect=[{},rows,[]]))
    stack.enter_context(patch.object(agent,'home_assistant_registry_metadata',return_value={}))
    for name in ('maintain_daily_pv_peak','shelly_daily_energy_inventory','device_daily_energy_inventory','period_energy_inventory','solar_forecast_inventory'):
     stack.enter_context(patch.object(agent,name,return_value=[]))
    result=agent.home_assistant_summary('fixture',full_inventory=full)
   for i,row in enumerate(result['inventory']):
    attrs=row['attributes'];self.assertNotIn('private_token',attrs)
    if i<3:self.assertEqual(attrs['state_class'],rows[i]['attributes']['state_class'])
    else:self.assertNotIn('state_class',attrs)
if __name__=='__main__' :unittest.main()
