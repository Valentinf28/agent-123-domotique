"""Native component unit tests with HA public interfaces stubbed, no hardware IO."""
import asyncio
from datetime import datetime,timezone,timedelta
from dataclasses import make_dataclass
import importlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock,patch

ROOT=Path(__file__).parents[1]/'agent_123_domotique/integrations/labox_ddzy422'
package=types.ModuleType('native_ddzy');package.__path__=[str(ROOT)];sys.modules['native_ddzy']=package
transport=importlib.import_module('native_ddzy.transport')

def module(name,**values):
 obj=types.ModuleType(name);obj.__dict__.update(values);sys.modules[name]=obj;return obj
module('homeassistant');module('homeassistant.helpers');module('homeassistant.components')
module('homeassistant.const',Platform=types.SimpleNamespace(SENSOR='sensor'),CONF_HOST='host')
network=module('homeassistant.components.network',async_get_adapters=AsyncMock(return_value=[{'enabled':True,'ipv4':[{'address':'192.168.6.10','network_prefix':24}]}]))
class Store:
 values={}
 def __init__(self,hass,version,key,**kw):self.key=key
 async def async_load(self):return self.values.get(self.key)
 async def async_save(self,value):self.values[self.key]=dict(value)
class Coordinator:
 def __init__(self,hass,*args,**kwargs):self.hass=hass;self.last_update_success=True;self.data=None
class CoordinatorEntity:
 def __init__(self,coordinator):self.coordinator=coordinator
 @property
 def available(self):return self.coordinator.last_update_success
class UpdateFailed(Exception):pass
module('homeassistant.helpers.storage',Store=Store)
module('homeassistant.helpers.update_coordinator',DataUpdateCoordinator=Coordinator,UpdateFailed=UpdateFailed,CoordinatorEntity=CoordinatorEntity)
module('homeassistant.helpers.entity',DeviceInfo=lambda **kw:kw)
classes=types.SimpleNamespace(**{k:k.lower() for k in ('POWER','ENERGY','VOLTAGE','CURRENT','FREQUENCY')})
module('homeassistant.components.sensor',SensorDeviceClass=classes,SensorEntity=type('SensorEntity',(),{}),SensorEntityDescription=make_dataclass('Description',[('key',str),('name',str),('device_class',object,None),('native_unit_of_measurement',object,None),('state_class',object,None)]),SensorStateClass=types.SimpleNamespace(MEASUREMENT='measurement',TOTAL_INCREASING='total_increasing'))
coordinator_module=importlib.import_module('native_ddzy.coordinator');sensor_module=importlib.import_module('native_ddzy.sensor')

class FakeSocket:
 def __init__(self,replies):self.replies=replies;self.sent=[];self.timeout=1
 def settimeout(self,value):self.timeout=value
 def sendto(self,value,peer):self.sent.append((value,peer))
 def recvfrom(self,size):
  if self.timeout<=.3:raise socket.timeout()
  if self.replies:return self.replies.pop(0)
  raise socket.timeout()
 def close(self):pass

class ProtocolTests(unittest.TestCase):
 def meter(self):
  with patch.object(transport.socket,'socket',return_value=FakeSocket([])):
   return transport.Meter('192.168.6.194',2616442643,'D42787012CD2')
 def test_crc_sign_and_only_measurement_functions(self):
  self.assertEqual(transport.crc16(b'123456789'),b'\x37\x4b');self.assertEqual(transport.signed_magnitude(0x800001cb,32),-459)
  meter=self.meter()
  for registers in ((1,1),(0,13),(14,21),(42,1)):
   with self.assertRaises(ValueError):meter.read(*registers)
  self.assertEqual(meter.sock.sent,[])
 def test_frames_wrong_source_crc_count_rejected(self):
  meter=self.meter();values=list(range(14));raw=bytes([1,3,28])+struct.pack('>14H',*values);valid=raw+transport.crc16(raw)
  bad=valid[:-1]+bytes([valid[-1]^1]);packet=lambda v:b'+ok='+v.hex().encode()+b'\r\n'
  meter.sock.replies=[(packet(valid),('192.168.6.193',48899)),(packet(bad),meter.addr),(packet(valid),meter.addr)]
  self.assertEqual(meter.read(0,14,tries=1),values);self.assertEqual(meter.stats['invalidFrames'],1);self.assertTrue(meter.sock.sent[0][0].startswith(b'AT+INVDATA=8,0103'))
 def test_bad_identity_or_public_address_refused(self):
  for values in [('8.8.8.8',1,'D42787012CD2'),('192.168.6.194',True,'D42787012CD2'),('192.168.6.194',1,'FFFFFFFFFFFF')]:
   with self.assertRaises(ValueError):transport.validate_settings(*values)
  meter=self.meter();meter.sock.replies=[(b'192.168.6.194,D42787012CD2,999',meter.addr)]
  with self.assertRaises(ValueError),patch.object(transport.time,'sleep'):meter.enter()
  self.assertEqual([p[0] for p in meter.sock.sent],[b'WIFIKIT-214028-READ'])
 def test_executor_clients_remain_serialized_even_without_async_lock(self):
  from concurrent.futures import ThreadPoolExecutor
  import time
  active=0;peak=0
  class FakeMeter:
   def __init__(self,*args):
    nonlocal active,peak
    active+=1;peak=max(active,peak)
   def enter(self):pass
   def sample(self):time.sleep(.01);return {'values':{},'readAtUtc':'now'}
   def close(self):
    nonlocal active
    active-=1
  settings={'host':'192.168.6.194','logger_serial':2616442643,'mac':'D42787012CD2'}
  with patch.object(transport,'Meter',FakeMeter),ThreadPoolExecutor(max_workers=2) as executor:
   list(executor.map(transport.read_sample,[settings,settings]))
  self.assertEqual(peak,1)
 def test_energy_reload_decrease_and_jump_are_not_zeroed(self):
  values={'importTotalKwh':3083.61,'exportTotalKwh':5667.90};guard=transport.IndexGuard();saved=guard.validate(values,1000)
  restored=transport.IndexGuard(json.loads(json.dumps(saved)))
  self.assertEqual(restored.validate(values|{'exportTotalKwh':5667.91},1030)['exportTotalKwh'],5667.91)
  checkpoint=dict(restored.previous)
  for bad in [values|{'importTotalKwh':0},values|{'exportTotalKwh':9000}]:
   with self.assertRaises(ValueError):restored.validate(bad,1060)
   self.assertEqual(restored.previous,checkpoint)

class NativeEntityTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  Store.values={};self.entry=types.SimpleNamespace(data={'host':'192.168.6.194','logger_serial':2616442643,'mac':'D42787012CD2'})
  self.coordinator=coordinator_module.MeterCoordinator(types.SimpleNamespace(),self.entry)
  await self.coordinator.async_load_indexes()
  self.sample={'readAtUtc':datetime.now(timezone.utc).isoformat(),'values':{'gridPowerW':-459,'importTotalKwh':3083.61,'exportTotalKwh':5667.90,'voltageV':238.3}}
  package.async_read=AsyncMock(return_value=self.sample)
 async def test_coordinator_persists_indexes_across_reload(self):
  self.coordinator.data=await self.coordinator._async_update_data()
  reloaded=coordinator_module.MeterCoordinator(types.SimpleNamespace(),self.entry);await reloaded.async_load_indexes()
  self.assertEqual(reloaded.guard.previous['exportTotalKwh'],5667.90)
  package.async_read=AsyncMock(return_value={'readAtUtc':datetime.now(timezone.utc).isoformat(),'values':self.sample['values']|{'importTotalKwh':0}})
  with self.assertRaises(UpdateFailed):await reloaded._async_update_data()
 async def test_poll_failure_is_unavailable_not_zero(self):
  package.async_read=AsyncMock(side_effect=TimeoutError('no packet'))
  with self.assertRaises(UpdateFailed):await self.coordinator._async_update_data()
  self.coordinator.last_update_success=False;self.coordinator.data=self.sample
  sensor=sensor_module.MeterSensor(self.coordinator,sensor_module.DESCRIPTIONS[0]);self.assertFalse(sensor.available);self.assertIsNone(sensor.native_value)
 async def test_negative_grid_is_export_with_stable_unique_id(self):
  self.coordinator.data=self.sample
  sensors=[sensor_module.MeterSensor(self.coordinator,d) for d in sensor_module.DESCRIPTIONS]
  self.assertEqual(sensors[0].native_value,-459);self.assertEqual(sensors[1].native_value,0);self.assertEqual(sensors[2].native_value,459)
  self.assertEqual(sensors[3].entity_description.state_class,'total_increasing')
  old=sensors[0]._attr_unique_id;self.coordinator.settings['host']='192.168.6.195'
  self.assertEqual(sensor_module.MeterSensor(self.coordinator,sensor_module.DESCRIPTIONS[0])._attr_unique_id,old)
 async def test_stale_samples_unavailable(self):
  self.coordinator.data=self.sample|{'readAtUtc':(datetime.now(timezone.utc)-timedelta(seconds=91)).isoformat()}
  sensor=sensor_module.MeterSensor(self.coordinator,sensor_module.DESCRIPTIONS[0]);self.assertFalse(sensor.available);self.assertIsNone(sensor.native_value)

class RuntimeWiringTests(unittest.IsolatedAsyncioTestCase):
 async def test_single_client_per_logger_even_during_concurrent_flow(self):
  spec=importlib.util.spec_from_file_location('runtime_ddzy',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
  runtime=importlib.util.module_from_spec(spec);sys.modules['runtime_ddzy']=runtime;spec.loader.exec_module(runtime)
  active=0;peak=0
  async def executor(reader,settings):
   nonlocal active,peak
   active+=1;peak=max(peak,active);await asyncio.sleep(.01);active-=1;return {'values':{}}
  hass=types.SimpleNamespace(data={},async_add_executor_job=executor)
  settings={'host':'192.168.6.194','logger_serial':2616442643,'mac':'D42787012CD2'}
  await asyncio.gather(runtime.async_read(hass,settings),runtime.async_read(hass,settings))
  self.assertEqual(peak,1)

if __name__=='__main__':unittest.main()
