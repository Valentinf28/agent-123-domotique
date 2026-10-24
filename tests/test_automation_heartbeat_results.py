import unittest
from unittest.mock import patch
import agent
import automation_edit
import test_automation_edit as edit_fixtures
import test_automation_create as create_fixtures

class AutomationHeartbeatResults(unittest.TestCase):
 def roundtrip(self,action,fixture,payload,method):
  original=getattr(automation_edit,method)
  def invoke(*args,**kwargs):return original(*args,**kwargs,**({'data':fixture.data} if method!='read' else {}))
  def request(url,**kwargs):
   kwargs.pop('token',None);kwargs.pop('timeout',None)
   return fixture.call(url.removeprefix(agent.SUPERVISOR_API),**kwargs)
  command={'id':'fixture-command','action':action,'payload':payload}
  with patch('installation_reset.blocks_mutations',return_value=False),patch.object(automation_edit,method,side_effect=invoke),patch.object(agent,'request_json',side_effect=request),patch.object(agent,'home_assistant_ws_command',side_effect=lambda _,p:fixture.ws(p)):
   result=agent.queued_command_result('fixture-token',command)
  self.assertTrue(result['ok'],result.get('error'))
  output=agent.command_result_for_heartbeat(command,result)
  with patch.object(agent,'request_json',return_value={}) as request:
   agent.heartbeat('https://fixture.invalid/api','fixture-token',{'commandResults':[output]})
   sent=request.call_args.kwargs['payload']['commandResults'][0]
  self.assertEqual(sent['result'],result['result']);self.assertEqual(sent['id'],command['id'])
  return sent['result']
 def prepare(self,cls):
  f=cls();f.setUp();self.addCleanup(f.tmp.cleanup);return f
 def test_read_native_configuration_and_digest_reaches_actual_heartbeat(self):
  f=self.prepare(edit_fixtures.AutomationEditTests);r=self.roundtrip('ha.automation.read',f,{'entityId':f.entity},'read');self.assertEqual(r['configDigest'],automation_edit.digest(f.initial));self.assertEqual(r['entityId'],f.entity)
 def test_update_ack_and_digest_reaches_actual_heartbeat(self):
  f=self.prepare(edit_fixtures.AutomationEditTests);r=self.roundtrip('ha.automation.update',f,f.payload,'update');self.assertTrue(r['updated']);self.assertEqual(r['configDigest'],automation_edit.digest(f.config))
 def test_delete_ack_reaches_actual_heartbeat(self):
  f=self.prepare(edit_fixtures.AutomationDeleteTests);r=self.roundtrip('ha.automation.delete',f,{'entityId':f.entity,'expectedDigest':automation_edit.digest(f.initial)},'delete');self.assertTrue(r['deleted'])
 def test_created_native_id_reaches_actual_heartbeat(self):
  f=self.prepare(create_fixtures.AutomationCreateTests);f.ws=lambda _:None;r=self.roundtrip('ha.automation.create',f,f.payload,'create');self.assertTrue(r['created']);self.assertEqual(r['entityId'],'automation.actual_native_identity')
 def test_unreviewed_or_failed_result_never_reaches_heartbeat(self):
  for action,ok in [('ha.proxy',True),('ha.automation.read',False)]:
   out=agent.command_result_for_heartbeat({'id':'fixture','action':action},{'ok':ok,'result':{'secret':'must-not-be-sent'}})
   self.assertNotIn('result',out)
 def test_privileged_recovery_never_becomes_queued_command(self):
  c={'id':'fixture','action':'installation.update.recovery','payload':{}}
  r=agent.queued_command_result('fixture-token',c);self.assertFalse(r['ok']);self.assertNotIn('result',agent.command_result_for_heartbeat(c,r))
if __name__=='__main__':unittest.main()
