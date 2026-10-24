"""Boot-file rollback and authentication regressions. No real disks, TTYs or host bus."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import pty
import termios
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'labox_boot_prepare'),str(ROOT/'labox_maintenance')]
import boot
from security import Attempts,Refused,generate,normalize,valid_configuration,verify
from session import Session
from host import Host,properties,UNIT
from terminal import Terminal

class BootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'boot';self.root.mkdir();self.path=self.root/'cmdline.txt';self.path.write_bytes(b'console=ttyAML0,115200n8 console=tty0 root=PARTUUID=private-fixture ro\n')
        self.backups=Path(self.tmp.name)/'backups';self.backups.mkdir()
        self.original=self.path.read_bytes();self.digest=boot.sha(self.original)
    def apply(self):return boot.apply(self.root,self.backups,'odroid-m1s','18.3',self.digest,'fixture-12345678')
    def test_plan_is_read_only_and_redacts_kernel_parameters(self):
        p=boot.plan(self.root,'odroid-m1s','18.3')
        self.assertTrue(p['changeRequired']);self.assertNotIn('private-fixture',json.dumps(p))
        self.assertEqual(self.path.read_bytes(),self.original);self.assertEqual(list(self.backups.iterdir()),[])
    def test_apply_backs_up_and_preserves_root_and_serial(self):
        result=self.apply();data=self.path.read_bytes()
        self.assertIn(b'root=PARTUUID=private-fixture ro',data);self.assertIn(b'console=ttyAML0,115200n8',data)
        for arg in boot.REQUIRED:self.assertEqual(data.decode().split().count(arg),1)
        folder=Path(result['backup']);self.assertEqual((folder/'cmdline.original').read_bytes(),self.original)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((folder/'cmdline.original').stat().st_mode),0o600)
    def test_all_normal_vt_gettys_masked_but_diagnostics_and_kiosk_unchanged(self):
        self.apply();text=self.path.read_text()
        for name in ('getty@.service','autovt@.service','ha-cli@.service'):self.assertIn('systemd.mask='+name,text)
        for name in ('serial-getty','journald','supervisor','docker','xorg','labox-maintenance'):self.assertNotIn('systemd.mask='+name,text)
    def test_idempotent_no_second_backup(self):
        self.apply();digest=boot.sha(self.path.read_bytes())
        r=boot.apply(self.root,self.backups,'odroid-m1s','18.3',digest,'fixture-12345678')
        self.assertFalse(r['changed']);self.assertEqual(len(list(self.backups.iterdir())),1)
    def test_exact_restore(self):
        r=self.apply();boot.restore(self.root,r['backup'],r['afterSha256'],'fixture-12345678')
        self.assertEqual(self.path.read_bytes(),self.original)
    def test_restore_refuses_wrong_device_or_altered_current_file(self):
        r=self.apply()
        with self.assertRaises(boot.Refused):boot.restore(self.root,r['backup'],r['afterSha256'],'different-device')
        self.path.write_bytes(self.path.read_bytes()+b' ')
        with self.assertRaises(boot.Refused):boot.restore(self.root,r['backup'],r['afterSha256'],'fixture-12345678')
    def test_corrupt_backup_refused(self):
        r=self.apply();(Path(r['backup'])/'cmdline.original').write_bytes(b'console=tty0\n')
        with self.assertRaises(boot.Refused):boot.restore(self.root,r['backup'],r['afterSha256'],'fixture-12345678')
    def test_stale_plan_refused(self):
        self.path.write_bytes(b'console=tty0 different=1\n')
        with self.assertRaises(boot.Refused):self.apply()
        self.assertEqual(list(self.backups.iterdir()),[])
    def test_unknown_machine_version_and_non_hdmi_refused(self):
        for machine,version in [('unknown','18.3'),('odroid-m1s','99.0')]:
            with self.assertRaises(boot.Refused):boot.plan(self.root,machine,version)
        with self.assertRaises(boot.Refused):boot.target(b'console=ttyS0\n')
    def test_newlines_quotes_controls_and_rescue_refused(self):
        for data in (b'console=tty0\ninit=bad\n',b'console=tty0 root="with spaces"\n',b'console=tty0\0',b'console=tty0 systemd.unit=rescue.target\n',b'console=tty0 debug\n'):
            with self.subTest(data=data),self.assertRaises(boot.Refused):boot.target(data)
    def test_source_change_between_plan_and_backup_is_refused(self):
        original_plan=boot.plan
        def changed(*args):
            value=original_plan(*args);self.path.write_bytes(b"console=tty0 changed=after-plan\n");return value
        with patch.object(boot,"plan",side_effect=changed),self.assertRaises(boot.Refused):self.apply()
        self.assertEqual(list(self.backups.iterdir()),[])
    def test_kernel_cmdline_length_is_bounded(self):
        with self.assertRaises(boot.Refused):boot.target(b"console=tty0 a="+b"x"*2000)

    def test_symbolic_and_hard_links_refused(self):
        self.path.unlink();self.path.symlink_to(self.backups/'some-file')
        with self.assertRaises(OSError):self.apply()
        self.path.unlink();self.path.write_bytes(self.original);os.link(self.path,self.root/'hardlink')
        with self.assertRaises(boot.Refused):self.apply()
    def test_backup_failure_prevents_boot_write(self):
        with patch.object(boot,'private_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.apply()
        self.assertEqual(self.path.read_bytes(),self.original)
    def test_refuses_backup_on_boot_partition(self):
        with self.assertRaises(boot.Refused):boot.apply(self.root,self.root,'odroid-m1s','18.3',self.digest,'fixture-12345678')
    def test_audit_after_upgrade_does_not_repair_silently(self):
        self.assertFalse(boot.audit(self.original)['parametersPresent']);self.apply();self.assertTrue(boot.audit(self.path.read_bytes())['parametersPresent'])
        self.path.write_bytes(self.original)
        self.assertFalse(boot.audit(self.path.read_bytes())['parametersPresent']);self.assertEqual(self.path.read_bytes(),self.original)
    def test_conflicting_owned_parameters_corrected_only(self):
        data=b'console=tty0 loglevel=7 systemd.show_status=yes unrelated=keep systemd.mask=other.service\n'
        value=boot.target(data);self.assertNotIn(b'loglevel=7',value);self.assertIn(b'unrelated=keep systemd.mask=other.service',value)

class CredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.options,cls.code=generate('a'*32)
    def test_generated_code_unique_and_hash_only(self):
        other,code=generate('a'*32);self.assertNotEqual(code,self.code);self.assertNotEqual(other['credential_hash'],self.options['credential_hash'])
        self.assertNotIn(self.code.replace('-',''),json.dumps(self.options))
        self.assertTrue(verify(self.options,self.code));self.assertFalse(verify(self.options,'0'*24))
    def test_machine_binding_and_hash_validation(self):
        valid_configuration(self.options,'a'*32)
        with self.assertRaises(Refused):valid_configuration(self.options,'b'*32)
        with self.assertRaises(Refused):valid_configuration({**self.options,'credential_hash':'bad'},'a'*32)
        self.assertFalse(verify({**self.options,'machine_id':'b'*32},self.code))
    def test_normalization_and_malformed_input(self):
        self.assertEqual(len(normalize(self.code)),24)
        for code in ('123','a'*24,None,'x'*500,'０'*24):self.assertIsNone(normalize(code))
    def test_rate_limit_survives_process_restart_and_host_reboot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'attempts';a=Attempts(p,'boot',clock=lambda:1000)
            for _ in range(5):a.failed()
            self.assertEqual(a.remaining(),60)
            self.assertEqual(Attempts(p,'boot',clock=lambda:1000).remaining(),60)
            self.assertEqual(Attempts(p,'newboot',clock=lambda:0).remaining(),600)
            a.succeeded();self.assertEqual(a.remaining(),0)
    def test_exponential_delay_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Attempts(Path(tmp)/'state','boot',clock=lambda:10)
            for _ in range(30):a.failed()
            self.assertEqual(a.remaining(),600)

class FakeHost:
    def __init__(self):self.starts=[];self.identity='a'*32
    async def machine_id(self):return self.identity
    async def start(self,return_vt):self.starts.append(return_vt)

class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.options,self.code=generate('a'*32);self.host=FakeHost();self.attempts=Attempts(Path(self.tmp.name)/'state','boot',clock=lambda:100)
        self.session=Session(self.options,self.host,self.attempts)
    async def test_no_native_session_before_authentication(self):
        with self.assertRaises(Refused):await self.session.open('0'*24)
        self.assertEqual(self.host.starts,[])
    async def test_correct_per_device_code_starts_session(self):
        result=await self.session.open(self.code,7);self.assertEqual(self.host.starts,[7]);self.assertEqual(result['maximumSeconds'],600)
    async def test_lockout_even_with_correct_code(self):
        for _ in range(5):self.attempts.failed()
        with self.assertRaises(Refused):await self.session.open(self.code)
        self.assertEqual(self.host.starts,[])
    async def test_copied_configuration_on_other_box_refused(self):
        self.host.identity='b'*32
        with self.assertRaises(Refused):await self.session.open(self.code)
        self.assertEqual(self.host.starts,[])
    async def test_host_unavailable_does_not_claim_success(self):
        async def fail(vt):raise Refused('unavailable')
        self.host.start=fail
        with self.assertRaises(Refused):await self.session.open(self.code)
    async def test_exact_transient_unit_without_shell_password_or_restart(self):
        p=dict(properties(7));self.assertEqual(p['TTYPath'].value,'/dev/tty8');self.assertEqual(p['RuntimeMaxUSec'].value,600_000_000)
        self.assertEqual(p['ExecStart'].value,[['/usr/sbin/haos-cli',['/usr/sbin/haos-cli'],False]])
        self.assertEqual(p['ExecStopPost'].value,[['/usr/bin/chvt',['/usr/bin/chvt','7'],True]])
        self.assertEqual(p['Restart'].value,'no');self.assertNotIn('Environment',p)
        for vt in (0,8,9,'7',True):
            with self.assertRaises(Refused):properties(vt)
    async def test_terminal_handoff_only_after_authentication(self):
        handoffs=[]
        with self.assertRaises(Refused):await self.session.open("0"*24,before_start=lambda:handoffs.append(True))
        self.assertEqual(handoffs,[])
        self.attempts.succeeded()
        await self.session.open(self.code,before_start=lambda:handoffs.append(True))
        self.assertEqual(handoffs,[True])

    async def test_no_broad_hardware_or_network_permissions(self):
        text=(ROOT/'labox_maintenance/config.yaml').read_text()
        self.assertIn('full_access: false',text);self.assertIn('host_pid: false',text);self.assertNotIn('SYS_ADMIN',text)
        self.assertIn('deny /dev/input/** rw',(ROOT/'labox_maintenance/apparmor.txt').read_text())


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.master,self.slave=pty.openpty();os.set_blocking(self.master,False);os.set_blocking(self.slave,False)
        self.tty=Terminal('a'*32,'fixture');self.tty.fd=self.slave;self.tty.original=termios.tcgetattr(self.slave)
        self.tty.active=lambda:8
    async def asyncTearDown(self):
        if self.tty.fd is not None:os.close(self.tty.fd)
        os.close(self.master)
    async def test_code_input_is_masked_and_handoff_closes_reader(self):
        self.tty.prompt();os.write(self.master,b'123456789012345678901234\r')
        code=await self.tty.read_code();self.assertEqual(code,'123456789012345678901234')
        output=os.read(self.master,8192)
        self.assertNotIn(code.encode(),output);self.assertIn(b'************************',output)
        self.tty.handoff();self.assertIsNone(self.tty.fd)
        with self.assertRaises(OSError):os.fstat(self.slave)
    async def test_cancel_does_not_produce_a_code_or_shell(self):
        self.tty.prompt();os.write(self.master,b'123\x03')
        self.assertIsNone(await self.tty.read_code())

if __name__=='__main__':unittest.main()
