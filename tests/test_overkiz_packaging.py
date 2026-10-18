import unittest,ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'agent_123_domotique'
class OverkizPackaging(unittest.TestCase):
 def test_setup_module_is_in_runtime_image(self):
  self.assertIn('COPY overkiz_setup.py /opt/agent/overkiz_setup.py',(ROOT/'Dockerfile').read_text())
 def test_secrets_cannot_enter_durable_queue_result(self):
  tree=ast.parse((ROOT/'agent.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='queued_command_result');module=ast.Module(body=[fn],type_ignores=[])
  def relay(*args):raise AssertionError('durable relay must not run')
  scope={'relay_command':relay,'Any':object};exec(compile(module,'queue-fixture','exec'),scope)
  self.assertFalse(scope['queued_command_result']('fake',{'action':'commissioning.overkiz','payload':{'password':'do-not-store'}})['ok'])
