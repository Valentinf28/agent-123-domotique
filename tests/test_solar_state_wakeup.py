import json,threading,unittest
from solar_state_wakeup import solar_entities,watch_session
class Socket:
 def __init__(self,messages):self.messages=iter(messages);self.sent=[]
 def recv(self):return json.dumps(next(self.messages))
 def send(self,value):self.sent.append(json.loads(value))
def event(entity='sensor.power',state='23',previous='22',kind='power'):
 return {'type':'event','id':1,'event':{'event_type':'state_changed','data':{'entity_id':entity,'old_state':{'state':previous},'new_state':{'state':state,'attributes':{'device_class':kind}}}}}
class WakeTests(unittest.TestCase):
 def test_only_enabled_solar_sensor_registry_rows_are_selected(self):
  rows=[{'entity_id':'sensor.power','platform':'solarman'},{'entity_id':'sensor.grid','platform':'labox_ddzy422'},{'entity_id':'sensor.other','platform':'tuya'},{'entity_id':'switch.control','platform':'solarman'},{'entity_id':'sensor.disabled','platform':'solarman','disabled_by':'user'}]
  self.assertEqual(solar_entities({'result':rows}),{'sensor.power','sensor.grid'});self.assertEqual(solar_entities(None),set())
 def test_changed_power_wakes_but_same_value_other_site_or_non_power_does_not(self):
  wake=threading.Event();socket=Socket([{'type':'auth_required'},{'type':'auth_ok'},{'type':'result','id':1,'success':True},event(entity='sensor.foreign'),event(state='22'),event(kind='energy'),event()])
  with self.assertRaises(StopIteration):watch_session(socket,'fixture',{'sensor.power'},wake)
  self.assertTrue(wake.is_set());self.assertEqual([x['type'] for x in socket.sent],['auth','subscribe_events']);self.assertEqual(socket.sent[1]['event_type'],'state_changed')
 def test_subscription_refusal_never_wakes(self):
  wake=threading.Event();socket=Socket([{'type':'auth_required'},{'type':'auth_ok'},{'type':'result','id':1,'success':False}])
  with self.assertRaisesRegex(RuntimeError,'Subscription refused'):watch_session(socket,'fixture',{'sensor.power'},wake)
  self.assertFalse(wake.is_set())
 def test_simultaneous_power_events_are_coalesced(self):
  from unittest.mock import Mock
  wake=Mock();socket=Socket([{'type':'auth_required'},{'type':'auth_ok'},event(),event(state='24'),event(state='25')])
  with self.assertRaises(StopIteration):watch_session(socket,'fixture',{'sensor.power'},wake,clock=lambda:100)
  wake.set.assert_called_once()
if __name__=='__main__':unittest.main()
