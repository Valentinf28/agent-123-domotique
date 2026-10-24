"""Streaming local full-backup verification; no archive is extracted or retained."""
import hashlib
import json
import re
def verify_supervisor_archive(slug, token):
    """Read the real local archive completely; validate tar headers and payloads."""
    import tarfile
    import gzip
    import urllib.request
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', slug):
        raise RuntimeError('BACKUP_ARCHIVE_INVALID')
    request = urllib.request.Request('http://supervisor/backups/' + slug + '/download', headers={'Authorization': 'Bearer ' + token})
    checksum = hashlib.sha256(); total = 0; metadata = None; homeassistant = False; members = set()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args): raise RuntimeError('REDIRECT_REFUSED')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
        class Reader:
            def read(self, size=-1):
                nonlocal total
                block = response.read(min(size if size >= 0 else 1024*1024, 1024*1024)); checksum.update(block); total += len(block)
                if total > 16*1024**3: raise RuntimeError('BACKUP_TOO_LARGE')
                return block
        reader = Reader()
        with tarfile.open(fileobj=reader, mode='r|*') as archive:
            for member in archive:
                name = member.name[2:] if member.name.startswith('./') else member.name
                if member.isfile():
                    members.add(name)
                    content = archive.extractfile(member)
                    if name == 'backup.json':
                        if member.size > 1024 * 1024: raise RuntimeError('BACKUP_ARCHIVE_INVALID')
                        metadata = json.loads(content.read())
                    elif name.endswith(('.tar.gz', '.tar')):
                        # Validate inner archives too, including gzip CRC/footer.
                        inner = gzip.GzipFile(fileobj=content) if name.endswith('.gz') else content
                        with tarfile.open(fileobj=inner, mode='r|') as nested:
                            for nested_member in nested:
                                if nested_member.isfile():
                                    nested_content = nested.extractfile(nested_member)
                                    while nested_content.read(1024 * 1024): pass
                        while inner.read(1024 * 1024): pass
                        if inner is not content: inner.close()
                    else:
                        while content.read(1024 * 1024): pass
                    if name in ('homeassistant.tar.gz', 'homeassistant.tar') and member.size > 0:
                        homeassistant = True
        # Consume trailing blocks so interrupted downloads fail before deletion.
        while reader.read(1024 * 1024): pass
    if (not isinstance(metadata, dict) or metadata.get('slug') != slug or metadata.get('type') != 'full'
            or not isinstance(metadata.get('homeassistant'), dict)
            or metadata['homeassistant'].get('exclude_database') is not False
            or not homeassistant or total <= 1024):
        raise RuntimeError('BACKUP_ARCHIVE_INVALID')
    addons = [a.get('slug') for a in metadata.get('addons', metadata.get('apps', []))
              if isinstance(a, dict) and isinstance(a.get('slug'), str)
              and any(a['slug'] + suffix in members for suffix in ('.tar.gz', '.tar'))]
    return {'verified': True, 'sha256': checksum.hexdigest(), 'bytes': total, 'addons': addons}
