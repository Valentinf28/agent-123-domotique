import struct
from unittest import TestCase,main
from unittest.mock import Mock, patch
from solar_identity import crc
from deye_topology import parse, power_modifier, read
import test_solar_setup as fixture
from test_solar_setup import PAYLOAD, ADAPTERS
from solar_setup import settings,configure
import json

SERIAL=123456;SEQ=19
def frame(mppt=3,phase=1,device=3):
 values=[0]*22;values[0]=device;values[18]=mppt*256+phase
 values[3:8]=struct.unpack('>5H',b'2409241490')
 rtu=bytes([1,3,44])+struct.pack('>22H',*values);rtu+=crc(rtu)
 result=b'\xa5'+struct.pack('<H',14+len(rtu))+b'\x10\x15'+bytes([SEQ,0])+struct.pack('<I',SERIAL)+bytes(14)+rtu
 return result+bytes([sum(result[1:])&255,0x15])
class TopologyTests(TestCase):
 def test_device_reported_count_is_used_and_invalid_identity_is_rejected(self):
  for count in (1,2,3,4):self.assertEqual(parse(frame(count),SEQ,SERIAL)['mppt'],count)
  for value in (frame(0),frame(5),frame(3,3),frame(3,1,5),frame()[:-1]+b'\0'):
   self.assertIsNone(parse(value,SEQ,SERIAL))
  self.assertIsNone(parse(frame(),SEQ+1,SERIAL));self.assertIsNone(parse(frame(),SEQ,SERIAL+1))
 def test_lp1_settings_never_guess_two_inputs(self):
  for topology in (None,{'loggerSerial':PAYLOAD['loggerSerial'],'mppt':True,'phase':1,'mod':0},{'loggerSerial':1,'mppt':3,'phase':1,'mod':0}):
   with self.assertRaises(ValueError):settings(PAYLOAD|{'model':'deye_lp1'},ADAPTERS,topology)
class PowerScaleTests(TestCase):
 def sample(self,output,grid,load,external=None,gen=0):
  values=[0]*26;values[0]=gen&65535;values[3]=grid&65535;values[6]=(grid if external is None else external)&65535;values[9]=output&65535;values[12]=load&65535;return values
 def test_coherent_ten_watt_registers_for_import_and_export(self):
  self.assertEqual(power_modifier(self.sample(272,5,32)),1)
  self.assertEqual(power_modifier(self.sample(3935,-359,40,-353)),1)
 def test_standard_one_watt_registers_do_not_get_multiplied(self):
  self.assertEqual(power_modifier(self.sample(272,50,322)),0)
  self.assertEqual(power_modifier(self.sample(4000,-3000,1000)),0)
 def test_night_inconsistent_ct_generator_and_incomplete_read_do_not_guess(self):
  for row in (self.sample(0,5,5),self.sample(400,5,32),self.sample(272,5,32,500),self.sample(272,5,32,gen=50),[0]*25):
   self.assertIsNone(power_modifier(row))
 def test_two_same_frame_balances_must_independently_confirm_the_scale(self):
  with patch('deye_topology._registers',side_effect=[(frame(),SEQ,()),(b'',1,self.sample(272,5,32)),(b'',2,self.sample(3935,-359,40,-353))]):
   self.assertEqual(read('192.168.9.2',SERIAL)['mod'],1)
  with patch('deye_topology._registers',side_effect=[(frame(),SEQ,()),(b'',1,self.sample(272,5,32)),(b'',2,self.sample(272,50,322))]):
   self.assertIsNone(read('192.168.9.2',SERIAL)['mod'])

class TopologyReconcileTests(TestCase):
 setUp=fixture.SolarSetupTests.setUp
 run_setup=fixture.SolarSetupTests.run_setup
 # Inherit setup fixtures but run only dedicated migration scenarios here.
 def test_existing_connection_options_are_preserved_and_only_topology_is_changed(self):
  payload=PAYLOAD|{'model':'deye_lp1'};topology={'loggerSerial':payload['loggerSerial'],'mppt':3,'phase':1,'mod':0}
  options=settings(payload,ADAPTERS,topology);options.pop('name');options['additional_options']['mppt']=2;options['additional_options'].pop('mod');options['additional_options']['battery_nominal_voltage']=51
  entry={'domain':'solarman','entry_id':'saved','options':options};self.storage.write_text(json.dumps({'data':{'entries':[entry]}}));before=self.storage.read_bytes()
  call=Mock(side_effect=[[{'entry_id':'saved'}],{'handler':'saved','flow_id':'options1','type':'form','step_id':'init','data_schema':[{'name':k} for k in options]},{'type':'create_entry'}])
  result=self.run_setup(call,payload);self.assertEqual(result['entryId'],'saved');self.assertEqual(call.call_args.args[0],'/config/config_entries/options/flow/options1')
  sent=call.call_args.kwargs['payload'];self.assertEqual(sent['additional_options']['mppt'],3);self.assertEqual(sent['additional_options']['battery_nominal_voltage'],51);self.assertEqual(self.storage.read_bytes(),before)
  retry=Mock(return_value=[{'entry_id':'saved'}])
  with self.assertRaisesRegex(RuntimeError,'encore en cours'):self.run_setup(retry,payload)
  self.assertEqual(retry.call_count,1)
  entry['options']=sent;self.storage.write_text(json.dumps({'data':{'entries':[entry]}}));self.assertEqual(self.run_setup(retry,payload)['entryId'],'saved')
 def test_verified_scale_updates_existing_lp1_without_changing_other_options(self):
  payload=PAYLOAD|{'model':'deye_lp1'};topology={'loggerSerial':payload['loggerSerial'],'mppt':3,'phase':1,'mod':1}
  options=settings(payload,ADAPTERS,topology);options.pop('name');options['additional_options']['mod']=0;options['additional_options']['battery_nominal_voltage']=51
  entry={'domain':'solarman','entry_id':'saved','options':options};self.storage.write_text(json.dumps({'data':{'entries':[entry]}}));before=self.storage.read_bytes()
  call=Mock(side_effect=[[{'entry_id':'saved'}],{'handler':'saved','flow_id':'scale1','type':'form','step_id':'init','data_schema':[{'name':k} for k in options]},{'type':'create_entry'}])
  configure(payload,ADAPTERS,call,config=self.config,data=self.data,topology_reader=lambda *_:topology)
  sent=call.call_args.kwargs['payload'];self.assertEqual(sent['additional_options'],{'mod':1,'phase':1,'mppt':3,'battery_nominal_voltage':51});self.assertEqual(self.storage.read_bytes(),before)
 def test_inconclusive_balance_preserves_existing_scale(self):
  payload=PAYLOAD|{'model':'deye_lp1'};topology={'loggerSerial':payload['loggerSerial'],'mppt':3,'phase':1,'mod':1}
  options=settings(payload,ADAPTERS,topology);options.pop('name');entry={'domain':'solarman','entry_id':'saved','options':options};self.storage.write_text(json.dumps({'data':{'entries':[entry]}}))
  call=Mock(return_value=[{'entry_id':'saved'}]);configure(payload,ADAPTERS,call,config=self.config,data=self.data,topology_reader=lambda *_:topology|{'mod':None});self.assertEqual(call.call_count,1)
 def test_unavailable_topology_cannot_submit_or_change_connection(self):
  call=Mock();reader=Mock(side_effect=RuntimeError('No hardware reply'))
  with self.assertRaises(RuntimeError):configure(PAYLOAD|{'model':'deye_lp1'},ADAPTERS,call,config=self.config,data=self.data,topology_reader=reader)
  call.assert_not_called()
if __name__=='__main__':main()
