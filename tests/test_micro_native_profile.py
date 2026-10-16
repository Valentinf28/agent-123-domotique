import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import yaml
import micro_setup
from solar_profile import MICRO_PROFILE,MICRO_PROFILE_SHA
from solar_setup import settings

ADAPTERS=[{'enabled':True,'ipv4':[{'address':'192.168.6.180','network_prefix':24}]}]
PAYLOAD={'host':'192.168.6.159','loggerSerial':3840836493,'mac':'40:2a:8f:0f:62:34'}
class MicroTests(unittest.TestCase):
 def test_managed_legacy_profile_migrates_atomically_but_foreign_profile_is_preserved(self):
  from solar_profile import ensure_profile,LEGACY_MICRO_PROFILE_SHA
  root=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,root)
  target=root/'inverter_definitions/custom';target.mkdir(parents=True)
  current=Path(__file__).parents[1]/'agent_123_domotique/profiles'/MICRO_PROFILE
  previous=current.read_text().replace('update_interval: 5','update_interval: 30')
  self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(),LEGACY_MICRO_PROFILE_SHA)
  (target/MICRO_PROFILE).write_text(previous);ensure_profile(root,MICRO_PROFILE)
  self.assertEqual((target/MICRO_PROFILE).read_bytes(),current.read_bytes());ensure_profile(root,MICRO_PROFILE)
  (target/MICRO_PROFILE).write_text('foreign profile')
  with self.assertRaisesRegex(RuntimeError,'conservé'):ensure_profile(root,MICRO_PROFILE)
  self.assertEqual((target/MICRO_PROFILE).read_text(),'foreign profile')
 def test_ac_profile_is_pinned_readonly_and_never_ddzy_v5(self):
  path=Path(__file__).parents[1]/'agent_123_domotique/profiles'/MICRO_PROFILE
  self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),MICRO_PROFILE_SHA)
  profile=yaml.safe_load(path.read_text());self.assertEqual(profile['default']['update_interval'],5)
  items={i['name']:i for group in profile['parameters'] for i in group['items']}
  self.assertEqual(items['Power']['registers'],[86,87]);self.assertEqual(items['Power']['scale'],.1)
  self.assertEqual(items['Total Production']['registers'],[63,64]);self.assertEqual(items['Total Production']['state_class'],'total_increasing')
  for item in items.values():self.assertNotIn('write',item);self.assertNotIn('controls',item);self.assertNotIn('function',item)
  self.assertFalse((path.parent/'solarman_ddzy422_readonly.yaml').exists())
 def test_micro_settings_have_correct_profile_and_mode(self):
  values=settings(PAYLOAD|{'model':'deye_micro'},ADAPTERS);self.assertEqual(values['lookup_file'],'custom/'+MICRO_PROFILE);self.assertEqual(values['additional_options']['mod'],0)
 def test_correct_mac_serial_ip_only_then_native_solar_flow(self):
  sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
  sock.recvfrom.return_value=(b'192.168.6.159,402A8F0F6234,3840836493',('192.168.6.159',48899));call=Mock()
  with patch.object(micro_setup.socket,'socket',return_value=sock),patch.object(micro_setup,'configure_solar',return_value={'entryId':'micro'}) as configure:
   self.assertEqual(micro_setup.configure(PAYLOAD,ADAPTERS,call)['entryId'],'micro')
  configure.assert_called_once();sock.sendto.assert_called_once_with(b'WIFIKIT-214028-READ',('192.168.6.159',48899))
 def test_wrong_device_identity_never_reaches_config_flow(self):
  sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
  sock.recvfrom.return_value=(b'192.168.6.159,402A8F0F6234,999',('192.168.6.159',48899))
  with patch.object(micro_setup.socket,'socket',return_value=sock),patch.object(micro_setup,'configure_solar') as configure:
   with self.assertRaises(RuntimeError):micro_setup.configure(PAYLOAD,ADAPTERS,Mock())
  configure.assert_not_called()

if __name__=='__main__':unittest.main()
