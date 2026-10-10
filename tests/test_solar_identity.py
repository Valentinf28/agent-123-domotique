import unittest,sys,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'agent_123_domotique'))
from solar_identity import crc,request,parse
class IdentityTests(unittest.TestCase):
 def frame(self,serial=2974839220):
  rtu=b'\x01\x03\x0a2406150574';rtu+=crc(rtu)
  frame=b'\xa5'+struct.pack('<H',14+len(rtu))+b'\x10\x15\x07\x00'+struct.pack('<I',serial)+bytes(14)+rtu
  return frame+bytes([sum(frame[1:])&255,0x15])
 def test_read_only_fixed_register_request(self):
  r=request(2974839220,7)
  self.assertEqual(r[26:32],bytes.fromhex('010300030005'))
 def test_exact_identity(self):
  self.assertEqual(parse(self.frame(),7,2974839220),{'loggerSerial':2974839220,'inverterSerial':'2406150574'})
 def test_wrong_identity_sequence_checksum_and_truncation(self):
  f=self.frame()
  for data,seq,serial in [(f,8,2974839220),(f,7,42),(f[:-1],7,2974839220),(f[:30]+bytes([f[30]^1])+f[31:],7,2974839220)]:
   self.assertIsNone(parse(data,seq,serial))
