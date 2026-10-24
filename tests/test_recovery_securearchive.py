import io,json,os,tarfile,unittest
from unittest.mock import patch
import recovery_securearchive as validator
from recovery_securearchive import verify_archive as _verify_archive,ArchiveRejected
def verify_archive(stream,key,slug,addon):
 return _verify_archive(stream,key,slug,addon,expected_addons=[addon],expected_folders=['ssl','share','media'])
from securetar import SecureTarArchive
KEY='fixture-key-not-a-real-secret-1234567890'
ADDON='test_agent';SLUG='fixture1'
def fixture(version=3,missing=None,metadata_change=None,content=b'fixture'*100,password=KEY,apps_field=False):
 data=io.BytesIO();metadata={'slug':SLUG,'type':'full','protected':True,'homeassistant':{'exclude_database':False},'addons':[{'slug':ADDON}],'folders':['ssl','share','media']};metadata.update(metadata_change or {})
 if apps_field:metadata['apps']=metadata.pop('addons')
 with SecureTarArchive(fileobj=data,mode='w',password=password,create_version=version) as archive:
  b=json.dumps(metadata).encode();m=tarfile.TarInfo('backup.json');m.size=len(b);archive.tar.addfile(m,io.BytesIO(b))
  for name in ['homeassistant',ADDON,*[folder.replace('/', '_') for folder in metadata['folders']],'supervisor']:
   if name==missing:continue
   with archive.create_tar(name+'.tar.gz',gzip=True) as inner:
    m=tarfile.TarInfo('data/file');m.size=len(content);inner.addfile(m,io.BytesIO(content))
 return data.getvalue()
class SecureArchiveTests(unittest.TestCase):
 def test_complete_v3_no_plaintext_output(self):
  result=verify_archive(io.BytesIO(fixture()),KEY,SLUG,ADDON);self.assertTrue(result['authenticated']);self.assertFalse(result['plaintextWritten']);self.assertFalse(result['restorationPerformed']);self.assertEqual(result['filesRead'],6)
 def test_short_native_password_is_validated_cryptographically(self):
  result=verify_archive(io.BytesIO(fixture(password='native-short')),'native-short',SLUG,ADDON)
  self.assertTrue(result['authenticated'])
 def test_wrong_key_and_slug_rejected(self):
  for key,slug in [(KEY+'x',SLUG),(KEY,'other')]:
   with self.subTest(slug=slug),self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(fixture()),key,slug,ADDON)
 def test_missing_addon_rejected(self):
  with self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(fixture(missing=ADDON)),KEY,SLUG,ADDON)
 def test_native_inventory_binding_refuses_missing_installed_components(self):
  for addons,folders in [([ADDON,'another_installed_app'],['ssl','share','media']),([ADDON],['ssl','share','media','another_folder'])]:
   with self.subTest(addons=addons),self.assertRaises(ArchiveRejected):
    _verify_archive(io.BytesIO(fixture()),KEY,SLUG,ADDON,expected_addons=addons,expected_folders=folders)
 def test_native_local_folder_aliases_map_to_archive_filenames(self):
  for local in ('addons/local','apps/local'):
   folders=['ssl','share','media',local]
   with self.subTest(local=local):
    result=_verify_archive(io.BytesIO(fixture(metadata_change={'folders':folders})),KEY,SLUG,ADDON,expected_addons=[ADDON],expected_folders=folders)
    self.assertIn(local,result['folders']);self.assertIn(local.replace('/','_'),result['components'])
 def test_v1_api_local_folder_alias_resolves_to_actual_archive_proof(self):
  for api,raw in [('addons/local','apps/local'),('apps/local','addons/local')]:
   folders=['ssl','share','media',raw];expected=['ssl','share','media',api]
   result=_verify_archive(io.BytesIO(fixture(metadata_change={'folders':folders},apps_field=True)),KEY,SLUG,ADDON,expected_addons=[ADDON],expected_folders=expected)
   self.assertIn(raw,result['folders']);self.assertIn(raw,result['expectedFolders'])
   self.assertTrue(set(result['expectedFolders'])<=set(result['folders']))
   self.assertIn(raw.replace('/','_'),result['components'])
   self.assertTrue(result['authenticated'])
 def test_alias_does_not_accept_missing_native_member_or_ambiguous_metadata(self):
  folders=['ssl','share','media','apps/local'];expected=['ssl','share','media','addons/local']
  for raw,missing in [(folders,'apps_local'),(['ssl','share','media','apps/local','addons/local'],None),(['ssl','share','media'],None)]:
   with self.subTest(folders=raw),self.assertRaises(ArchiveRejected):
    _verify_archive(io.BytesIO(fixture(metadata_change={'folders':raw},missing=missing)),KEY,SLUG,ADDON,expected_addons=[ADDON],expected_folders=expected)
  with self.assertRaises(ArchiveRejected):
   _verify_archive(io.BytesIO(fixture(metadata_change={'folders':folders})),KEY+'wrong',SLUG,ADDON,expected_addons=[ADDON],expected_folders=expected)
  for requested in [expected+['apps/local'],['ssl','share','media','local_apps'],['ssl','share','media','apps/config']]:
   with self.subTest(expected=requested),self.assertRaises(ArchiveRejected):
    _verify_archive(io.BytesIO(fixture(metadata_change={'folders':folders})),KEY,SLUG,ADDON,expected_addons=[ADDON],expected_folders=requested)
 def test_database_exclusion_rejected(self):
  with self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(fixture(metadata_change={'homeassistant':{'exclude_database':True}})),KEY,SLUG,ADDON)
 def test_legacy_not_claimed_authenticated(self):
  with self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(fixture(version=2)),KEY,SLUG,ADDON)
 def test_cipher_tamper_rejected_without_parser_details(self):
  raw=bytearray(fixture());at=raw.index(b'SecureTar\x03');raw[at+150]^=1
  with self.assertRaises(ArchiveRejected) as caught:verify_archive(io.BytesIO(raw),KEY,SLUG,ADDON)
  self.assertNotIn(KEY,str(caught.exception));self.assertNotIn('data/file',str(caught.exception))
 def test_late_cipher_damage_is_not_mistaken_for_valid_password(self):
  raw=bytearray(fixture(content=os.urandom(1200000)))
  with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
   member=tar.getmember('homeassistant.tar.gz');raw[member.offset_data+member.size-1]^=1
  # Password-only early read succeeds, while full verification must reject.
  with SecureTarArchive(fileobj=io.BytesIO(raw),password=KEY) as archive:
   member=archive.tar.getmember('homeassistant.tar.gz');self.assertTrue(archive.validate_password(member))
  with self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(raw),KEY,SLUG,ADDON)
 def test_ciphertext_size_limit(self):
  with patch.object(validator,'MAX_CIPHERTEXT',1024),self.assertRaises(ArchiveRejected):
   verify_archive(io.BytesIO(fixture()),KEY,SLUG,ADDON)
 def test_compressed_bomb_respects_plaintext_limit(self):
  raw=fixture(content=b'x'*(2*1024*1024))
  self.assertLess(len(raw),200000)
  with patch.object(validator,'MAX_PLAINTEXT',1024*1024),self.assertRaises(ArchiveRejected):
   verify_archive(io.BytesIO(raw),KEY,SLUG,ADDON)
 def test_nonseekable_source_refused(self):
  class NonSeek(io.BytesIO):
   def seekable(self):return False
  with self.assertRaises(ArchiveRejected):verify_archive(NonSeek(fixture()),KEY,SLUG,ADDON)
 def test_authenticated_truncation_rejected(self):
  raw=fixture();at=raw.rindex(b'SecureTar\x03')
  with self.assertRaises(ArchiveRejected):verify_archive(io.BytesIO(raw[:at+145]),KEY,SLUG,ADDON)
if __name__=='__main__':unittest.main()
