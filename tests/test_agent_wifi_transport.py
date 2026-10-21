import importlib.util
from pathlib import Path
import sys,types,unittest
from unittest.mock import patch
sys.modules.setdefault('websocket',types.ModuleType('websocket'))
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
spec=importlib.util.spec_from_file_location('wifi_agent',Path(__file__).parents[1]/'agent_123_domotique/agent.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
import wifi_setup
class Transport(unittest.TestCase):
 def test_wifi_is_never_queued(self):
  with patch.object(agent,'relay_command') as dispatch:
   self.assertFalse(agent.queued_command_result('token',{'action':'commissioning.wifi'})['ok']);dispatch.assert_not_called()
 def test_supervisor_is_internal_and_result_redacts_secrets(self):
  with patch.object(agent,'request_json',return_value={'result':'ok','data':{'interfaces':[]}}) as request:
   result=agent.relay_command('token',{'action':'commissioning.wifi','payload':{'operation':'status','ownerScope':'a'*64}})
   self.assertTrue(result['ok']);request.assert_called_once_with('http://supervisor/network/info',token='token')
 def test_failures_cannot_echo_credentials(self):
  with patch.object(agent,'request_json',side_effect=RuntimeError('SECRET password')):
   result=agent.relay_command('token',{'action':'commissioning.wifi','payload':{'operation':'status','ownerScope':'a'*64}})
   self.assertFalse(result['ok']);self.assertNotIn('SECRET',str(result))
