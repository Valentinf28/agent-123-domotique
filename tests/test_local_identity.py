import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent_123_domotique'))
import tempfile
import unittest
from local_identity import load_key, proof, valid_origin
class IdentityTests(unittest.TestCase):
    def test_key_persists_and_proof_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'key'
            key=load_key(path)
            message='123home-local-v1\n'+'a'*64+'\nhttp://192.168.6.180'
            result=proof(key,'a'*64,'http://192.168.6.180',{'192.168.6.180'})
            load_key(path).public_key().verify(bytes.fromhex(result['signature']),message.encode())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_other_host_and_bad_challenge_rejected(self):
        for origin in ['http://192.168.6.181','http://evil.test','http://192.168.6.180:9000','http://user@192.168.6.180','http://192.168.6.180/path']:
            self.assertFalse(valid_origin(origin,{'192.168.6.180'}))
        with self.assertRaises(ValueError):proof(None,'bad','http://192.168.6.180',{'192.168.6.180'})
