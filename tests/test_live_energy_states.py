import unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
from live_energy_states import live_energy_states

class LiveEnergyTest(unittest.TestCase):
 def setUp(self):
  self.old={'entity_id':'sensor.pv','state':'0','attributes':{'device_class':'power','unit_of_measurement':'W'},'last_reported':'2026-10-21T00:00:00+00:00'}
  self.fresh={**self.old,'last_reported':'2026-10-22T11:40:00+00:00','last_updated':self.old['last_reported']}
 def test_stable_zero_uses_real_report_date(self):
  result=live_energy_states([self.old],lambda t:json.dumps([self.fresh]))
  self.assertEqual(result[0],self.fresh);self.assertEqual(self.old['last_reported'],'2026-10-21T00:00:00+00:00')
 def test_fresh_unavailable_is_preserved(self):
  self.assertEqual(live_energy_states([self.old],lambda t:[{**self.fresh,'state':'unavailable'}])[0]['state'],'unavailable')
 def test_foreign_duplicate_invalid_dates_fail_closed(self):
  for rows in [[{**self.fresh,'entity_id':'sensor.foreign'}],[self.fresh,self.fresh],[{**self.fresh,'last_reported':'bad'}],[{**self.fresh,'last_reported':'2026-10-22T11:40:00'}]]:
   self.assertEqual(live_energy_states([self.old],lambda t:rows),[self.old])
 def test_failed_template_keeps_old_evidence(self):
  def fail(t):raise RuntimeError('offline')
  self.assertEqual(live_energy_states([self.old],fail),[self.old])
 def test_only_valid_sensor_ids_and_energy_units(self):
  evil={**self.old,'entity_id':"sensor.bad'}}{{"};calls=[]
  self.assertEqual(live_energy_states([evil],lambda t:calls.append(t)),[evil]);self.assertEqual(calls,[])
 def test_soc_and_nonenergy_rows(self):
  soc={**self.old,'entity_id':'sensor.storage','state':'20','attributes':{'device_class':'battery','unit_of_measurement':'%'}}
  unrelated={'entity_id':'sensor.weather','state':'15','attributes':{'device_class':'temperature','unit_of_measurement':'°C'}}
  result=live_energy_states([soc,unrelated],lambda t:[{**soc,'last_reported':self.fresh['last_reported']}]);self.assertEqual(result[1],unrelated)
if __name__=='__main__':unittest.main()
