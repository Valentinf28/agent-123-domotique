import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
if 'websocket' not in sys.modules:sys.modules['websocket']=types.ModuleType('websocket')
spec=importlib.util.spec_from_file_location('solar_guard_agent',Path(__file__).parents[1]/'agent_123_domotique/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)

class SolarMeasurementGuard(unittest.TestCase):
    def build(self, grid_payload=None):
        payload={'gridPowerEntityId':'sensor.grid','chargerStateEntityId':'sensor.ev_state',
                 'chargerCurrentEntityId':'sensor.ev_current','chargerVoltageEntityId':'sensor.ev_voltage',
                 'dynamicLimitEntityId':'number.ev_limit','startButtonEntityId':'button.ev_start',
                 'stopButtonEntityId':'button.ev_stop','batteryPowerEntityId':'sensor.battery_power',
                 'batteryLevelEntityId':'sensor.battery_soc'}
        payload.update(grid_payload or {})
        states=[{'entity_id':v,'state':'0'} for k,v in payload.items() if k.endswith('EntityId')]
        states += [{'entity_id':entity,'state':'0'} for entity in payload.get('gridPowerEntityIds', [])]
        calls=[]
        def request(url,**kwargs):
            calls.append((url,kwargs))
            return states if url.endswith('/states') else {}
        with patch.object(agent,'home_assistant_ws_command',return_value={'result':[]}),patch.object(agent,'request_json',side_effect=request),patch.object(agent,'deye_vehicle_export_automation',return_value=None):
            result=agent.relay_command('token',{'id':'test','action':'ha.ev_charger.solar_plan','payload':payload})
        self.assertTrue(result['ok'],result)
        return next(kwargs['payload'] for url,kwargs in calls if '/config/automation/config/ma_maison_lektrico_solar_charging' in url)

    def test_invalid_readings_stop_charging_before_any_setpoint_change(self):
        automation=self.build()
        first=automation['action'][0]['choose'][0]
        self.assertEqual(first['sequence'],[{'service':'button.press','target':{'entity_id':'button.ev_stop'}}])
        condition=first['conditions'][1]['value_template']
        for entity in ('grid','ev_voltage','ev_current','battery_power','battery_soc'):
            self.assertIn("is_number(states('sensor."+entity+"'))",condition)
        self.assertIn('last_reported',condition);self.assertIn('<= 180',condition)
        self.assertEqual(first['conditions'][0]['state'],'charging')

    def test_start_and_adjustment_require_recent_measurements(self):
        automation=self.build()
        branches=automation['action'][0]['choose']
        for branch in branches:
            if any(action.get('service')=='number.set_value' for action in branch['sequence']):
                checks=' '.join(condition.get('value_template','') for condition in branch['conditions'])
                self.assertIn('last_reported',checks)
                self.assertIn('<= 180',checks)
        self.assertTrue(any(trigger.get('seconds')=='/5' for trigger in automation['trigger']))

    def test_three_phases_are_used_in_every_grid_calculation(self):
        automation = self.build({'gridPowerEntityId':'sensor.home_configured_grid_power',
                                 'gridPowerEntityIds':['sensor.a','sensor.b','sensor.c'],
                                 'gridPowerMultiplier':-1})
        import json
        text = json.dumps(automation)
        self.assertNotIn('sensor.home_configured_grid_power', text)
        for phase in ('a','b','c'):
            self.assertIn("is_number(states('sensor." + phase + "'))", text)
        start = next(trigger for trigger in automation['trigger'] if trigger['id']=='demarrage')['value_template']
        stop = next(trigger for trigger in automation['trigger'] if trigger['id']=='arret_import')['value_template']
        for template in (start, stop):
            for phase in ('a','b','c'): self.assertIn("states('sensor." + phase + "')", template)
            self.assertIn('* -1', template)
            self.assertIn('1000 if', template)
            self.assertIn("in ['w', 'kw']", template)
        self.assertIn('last_reported', automation['action'][0]['choose'][0]['conditions'][1]['value_template'])

    def test_invalid_mapping_is_rejected_before_generation(self):
        for sources in ([], ['sensor.a','sensor.b'], ['sensor.a']*3, ['switch.a'], ['sensor.a\'bad'], ['sensor.home_configured_grid_power']):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                agent.grid_automation_sources({'gridPowerEntityIds':sources})
        for multiplier in (0,2,True,'-1'):
            with self.subTest(multiplier=multiplier), self.assertRaises(ValueError):
                agent.grid_automation_sources({'gridPowerEntityId':'sensor.a','gridPowerMultiplier':multiplier})

if __name__=='__main__':unittest.main()
