"""Qualification-only native SecureTar verifier. Never extracts plaintext to disk."""
import gzip
import hashlib
import json
from pathlib import PurePosixPath
import tarfile
from securetar import SecureTarArchive

class ArchiveRejected(Exception):
    pass

MAX_CIPHERTEXT = 5 * 1024**3
MAX_PLAINTEXT = 32 * 1024**3
BLOCK = 1024**2

def verify_archive(stream, password, expected_slug, expected_addon, *, expected_addons, expected_folders):
    """Verify an encrypted, seekable private archive with its own supplied key.

    Production integration must execute only inside the Box, bind the key and
    archive to owner/operation, and preserve the encrypted file until commit.
    This pure verifier performs no restore, upload, extraction or journal write.
    """
    try:
        return _verify(stream, password, expected_slug, expected_addon, expected_addons, expected_folders)
    except Exception:
        # Neither password, metadata, file paths nor native parser detail escape.
        raise ArchiveRejected('Archive chiffrée non vérifiée.') from None

def _verify(stream, password, expected_slug, expected_addon, expected_addons, expected_folders):
    if not isinstance(password, str) or not 1 <= len(password) <= 4096:
        raise ValueError()
    if (not isinstance(expected_addons, list) or expected_addon not in expected_addons
            or not isinstance(expected_folders, list) or any(not isinstance(x, str) for x in expected_addons+expected_folders)):
        raise ValueError()
    if not stream.seekable():
        raise ValueError()
    checksum = hashlib.sha256(); total = 0
    stream.seek(0)
    while chunk := stream.read(BLOCK):
        total += len(chunk)
        if total > MAX_CIPHERTEXT: raise ValueError()
        checksum.update(chunk)
    if total < 1024: raise ValueError()
    stream.seek(0)
    names=set(); components=set(); metadata=None; plain_total=0; files=0
    decompressed_total=0
    class BoundedReader:
        def __init__(self, source): self.source=source
        def read(self, size=-1):
            nonlocal decompressed_total
            chunk=self.source.read(size)
            decompressed_total+=len(chunk)
            if decompressed_total>MAX_PLAINTEXT:raise ValueError()
            return chunk
    with SecureTarArchive(fileobj=stream, mode='r', password=password) as archive:
        for member in archive.tar:
            name=member.name.removeprefix('./')
            if (not member.isfile() or name in names or '/' in name or '\\' in name
                    or name in ('', '.', '..')): raise ValueError()
            names.add(name)
            if name=='backup.json':
                if member.size>1024**2: raise ValueError()
                metadata=json.load(archive.tar.extractfile(member));continue
            if not name.endswith(('.tar','.tar.gz')): raise ValueError()
            encrypted=archive.tar.extractfile(member)
            # v3 authenticates every byte including the final record. Legacy
            # CBC is not labelled fully authenticated by this new verifier.
            if encrypted.read(10)!=b'SecureTar\x03':raise ValueError()
            encrypted.close()
            with archive.extract_tar(member) as decrypted:
                inner=gzip.GzipFile(fileobj=decrypted) if name.endswith('.gz') else decrypted
                bounded=BoundedReader(inner)
                with tarfile.open(fileobj=bounded,mode='r|') as contents:
                    for entry in contents:
                        if entry.size<0:raise ValueError()
                        plain_total += entry.size
                        if plain_total>MAX_PLAINTEXT:raise ValueError()
                        if entry.isfile():
                            data=contents.extractfile(entry);read=0
                            while chunk:=data.read(BLOCK):read+=len(chunk)
                            if read!=entry.size:raise ValueError()
                            files+=1
                # Consume gzip CRC and the authenticated final SecureTar record.
                while bounded.read(BLOCK):pass
                if inner is not decrypted:inner.close()
                while decrypted.read(BLOCK):pass
            components.add(name[:-7] if name.endswith('.tar.gz') else name[:-4])
    if not isinstance(metadata,dict) or metadata.get('slug')!=expected_slug or metadata.get('type')!='full' or metadata.get('protected') is not True:raise ValueError()
    ha=metadata.get('homeassistant')
    if not isinstance(ha,dict) or ha.get('exclude_database') is not False:raise ValueError()
    addons=metadata.get('addons',metadata.get('apps',[]));folders=metadata.get('folders',[])
    if not isinstance(addons,list) or not isinstance(folders,list):raise ValueError()
    addon_names=[a.get('slug') for a in addons if isinstance(a,dict)]
    if len(addon_names)!=len(addons) or expected_addon not in addon_names:raise ValueError()
    # Supervisor serializes folder names by replacing '/' with '_'.
    # Keep the native names in the proof; only map archive member names.
    if any(not isinstance(f,str) or f not in {'media','share','ssl','addons/local','apps/local'} for f in folders):raise ValueError()
    expected=set(addon_names)|{folder.replace('/', '_') for folder in folders}|{'homeassistant'}
    if not expected<=components or not set(expected_addons)<=set(addon_names) or not set(expected_folders)<=set(folders):raise ValueError()
    # Detect a changed file between checksum and parser passes.
    stream.seek(0);after=hashlib.sha256()
    while chunk:=stream.read(BLOCK):after.update(chunk)
    if checksum.digest()!=after.digest():raise ValueError()
    return {'verified':True,'authenticated':True,'cipherVersion':3,'sha256':checksum.hexdigest(),
            'bytes':total,'addons':addon_names,'components':sorted(components),'filesRead':files,
            'plaintextWritten':False,'restorationPerformed':False,'restorationVerified':False,
            'format':'home-assistant-tar','backupId':expected_slug,'full':True,'encrypted':True,
            'homeassistant':True,'database':True,'expectedAddons':expected_addons,
            'folders':folders,'expectedFolders':expected_folders,'keyState':'available'}
