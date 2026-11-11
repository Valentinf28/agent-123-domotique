import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent_123_domotique'))
from energy_engine import EnergyEngine, ENTITY_ID, iso
from agent import validate_local_energy
import agent

NOW = 1794398400.0
MICRO = 'sensor.1_2_3_home_deye_1234567890_power'


def row(entity_id, watts, **attributes):
    return {'entity_id': entity_id, 'state': str(watts), 'last_reported': iso(NOW),
            'attributes': {'unit_of_measurement': 'W', 'device_class': 'power', **attributes}}


def rows():
    return [row(MICRO, 2000, platform='solarman', model='M100G4 / M200G4',
                original_name='Power', serial_number='1234567890'), row('sensor.grid', -1000)]


def document():
    return {'agentId': 'box-a', 'installationId': 'house-a', 'revision': 'a' * 64,
            'configuration': {'electricalSupply': 'single', 'energyMetering': {
                'version': 1, 'confirmed': True, 'scope': 'site', 'name': 'Site', 'supply': 'single',
                'productionMode': 'devices', 'production': [MICRO], 'grid': ['sensor.grid'],
                'gridDirection': 'import_positive', 'batteryMode': 'none', 'battery': [],
                'batteryDirection': 'discharge_positive'}}}


class EnergyEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = EnergyEngine(validate_local_energy)

    def test_signed_balance_and_delayed_values_preserve_time(self):
        good = self.engine.calculate(document(), rows(), NOW)
        self.assertEqual(good['values'], {'solar': 2000, 'grid': -1000, 'home': 1000, 'battery': None})
        bad = rows(); bad[1]['state'] = '-5509'
        for elapsed in (5, 60, 120, 600):
            for source in bad: source['last_reported'] = iso(NOW + elapsed)
            result = self.engine.calculate(document(), bad, NOW + elapsed)
            self.assertEqual(result['status'], 'delayed')
            self.assertEqual(result['values'], good['values'])
            self.assertEqual(result['measuredAt'], iso(NOW))
        for source in bad: source['last_reported'] = iso(NOW + 601)
        self.assertEqual(self.engine.calculate(document(), bad, NOW + 601)['status'], 'unavailable')

    def test_missing_stale_duplicates_and_unknown_never_reuse_measurement(self):
        for mutate in (lambda x: x.pop(), lambda x: x.append(copy.deepcopy(x[0])),
                       lambda x: x[0].update(state='unavailable'),
                       lambda x: x[0].update(last_reported=iso(NOW-121)),
                       lambda x: x[0]['attributes'].update(stale=True),
                       lambda x: x[0].update(last_reported=iso(NOW+31)),
                       lambda x: x[0]['attributes'].update(unit_of_measurement='kWh')):
            self.engine.calculate(document(), rows(), NOW)
            bad = rows(); mutate(bad)
            self.assertEqual(self.engine.calculate(document(), bad, NOW)['status'], 'unavailable')

    def test_new_configuration_or_box_cannot_reuse_prior_balance(self):
        for field in ('revision', 'installationId', 'agentId'):
            self.engine.calculate(document(), rows(), NOW)
            changed = document(); changed[field] = 'changed'
            bad = rows(); bad[1]['state'] = '-5509'
            self.assertEqual(self.engine.calculate(changed, bad, NOW)['status'], 'unavailable')

    def test_import_unit_conversion_and_meter_direction(self):
        data = rows(); data[0]['state'] = '2'; data[0]['attributes']['unit_of_measurement'] = 'kW'
        data[1]['state'] = '-100'
        doc = document(); doc['configuration']['energyMetering']['gridDirection'] = 'export_positive'
        result = self.engine.calculate(doc, data, NOW)
        self.assertEqual(result['values']['home'], 2100)

    def test_separate_ac_battery_signed_and_unknown_battery(self):
        doc = document(); cfg = doc['configuration']['energyMetering']
        cfg.update(batteryMode='separate_ac', battery=['sensor.battery'], batteryDirection='charge_positive')
        result = self.engine.calculate(doc, rows() + [row('sensor.battery', 300)], NOW)
        self.assertEqual(result['values']['home'], 700)
        cfg.update(batteryMode='unknown', battery=[])
        self.assertEqual(self.engine.calculate(doc, rows(), NOW)['status'], 'unavailable')

    def test_hybrid_uses_ac_for_consumption_and_pv_for_production(self):
        doc = document(); cfg = doc['configuration']['energyMetering']
        pv = 'sensor.1_2_3_home_deye_54321_pv_power'; ac = pv.replace('_pv_power', '_power')
        cfg['production'].append(pv); cfg.update(hybrid=[{'production': pv, 'ac': ac}], batteryMode='coupled_dc')
        data = rows() + [row(pv, 800, platform='solarman', original_name='PV Power', model='SG0*HP3', serial_number='54321'),
                         row(ac, 500, platform='solarman', original_name='Power', model='SG0*HP3', serial_number='54321')]
        result = self.engine.calculate(doc, data, NOW)
        self.assertEqual(result['values']['solar'], 2800)
        self.assertEqual(result['values']['home'], 1500)
        data[-1]['attributes']['serial_number'] = 'wrong'
        self.assertEqual(self.engine.calculate(doc, data, NOW)['status'], 'unavailable')

    def test_night_standby_remains_explicitly_estimated(self):
        data = rows(); data[0]['state'] = 'unavailable'; data[1]['state'] = '300'
        data.append({'entity_id': 'sun.sun', 'state': 'below_horizon', 'last_reported': iso(NOW), 'attributes': {}})
        result = self.engine.calculate(document(), data, NOW)
        self.assertEqual(result['status'], 'estimated')
        self.assertEqual(result['values']['home'], 300)
        self.assertEqual(result['values']['solar'], 0)
        self.assertIsNone(self.engine.previous)

    def test_section_and_overlap_are_not_a_whole_home_balance(self):
        doc = document(); doc['configuration']['energyMetering']['scope'] = 'section'
        self.assertEqual(self.engine.calculate(doc, rows(), NOW)['status'], 'unconfigured')
        data = rows(); data[1]['attributes']['source_entity_ids'] = [MICRO]
        self.assertEqual(self.engine.calculate(document(), data, NOW)['status'], 'unavailable')

    def test_publication_is_a_reading_and_has_no_physical_control(self):
        doc = document(); identity = {'agent_id': 'box-a'}
        def read(path, default): return doc if path == agent.LOCAL_CONFIGURATION_PATH else identity
        with patch.object(agent, 'read_json', side_effect=read), patch.object(agent, 'request_json', return_value={}) as call, patch.object(agent, 'ENERGY_ENGINE', None):
            agent.publish_energy_balance('fixture', rows(), {})
        self.assertEqual(call.call_count, 1)
        self.assertTrue(call.call_args.args[0].endswith('/states/' + ENTITY_ID))
        self.assertEqual(call.call_args.kwargs['method'], 'POST')
        self.assertIn('energy_balance', call.call_args.kwargs['payload']['attributes'])


if __name__ == '__main__': unittest.main()
