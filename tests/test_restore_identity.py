import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_enrollment_retry import agent

class RestoreIdentityTests(unittest.TestCase):
 def test_restore_and_restart(self):
  identity={'agent_id':'box_test','token':'a'*64,'house_id':'installation_test'}
  with tempfile.TemporaryDirectory() as d,patch.object(agent,'STATE_PATH',Path(d)/'state.json'),patch.object(agent,'fetch_relay_configuration',return_value={'houseId':'installation_test'}) as request:
   result=agent.restore_identity('https://portal.test/api',json.dumps(identity))
   self.assertEqual(result,{'agent_id':'box_test','token':'a'*64})
   self.assertEqual(agent.STATE_PATH.stat().st_mode&0o777,0o600)
   self.assertEqual(agent.restore_identity('https://portal.test/api',json.dumps(identity)),result)
   request.assert_called_once()
 def test_wrong_house_or_existing_identity_never_written(self):
  identity=json.dumps({'agent_id':'box_test','token':'a'*64,'house_id':'installation_test'})
  with patch.object(agent,'write_state') as write,patch.object(agent,'fetch_relay_configuration',return_value={'houseId':'installation_other'}) as request:
   for state in ({},{'pending_enrollment':{}},{'agent_id':'box_other','token':'b'*64}):
    with patch.object(agent,'read_json',return_value=state):
     with self.assertRaises(RuntimeError):agent.restore_identity('https://portal.test/api',identity)
   write.assert_not_called();request.assert_called_once()
 def test_malformed_or_failed_validation_never_written(self):
  with patch.object(agent,'read_json',return_value={}),patch.object(agent,'write_state') as write,patch.object(agent,'fetch_relay_configuration',side_effect=TimeoutError()) as request:
   for text in ('[]','null','{}','not-json','x'*2049):
    with self.assertRaises(RuntimeError):agent.restore_identity('https://portal.test/api',text)
   request.assert_not_called()
   with self.assertRaises(TimeoutError):agent.restore_identity('https://portal.test/api',json.dumps({'agent_id':'box_test','token':'a'*64,'house_id':'installation_test'}))
   write.assert_not_called()
