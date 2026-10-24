"""Fixed-origin HTTP adapters. Never follow redirects carrying device credentials."""
import asyncio
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from native_backup_export import CHUNK_BYTES, ExportRejected

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExportRejected('REDIRECT_REFUSED')

class FixedTransport:
    def __init__(self, origin, credential):
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or parsed.netloc not in ('client.labox.eco','home.123panneaux-solaires.fr') or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:
            raise ExportRejected('INVALID_PORTAL_ORIGIN')
        self.origin=origin.rstrip('/');self.credential=credential;self.opener=urllib.request.build_opener(NoRedirect())
    def _request(self,method,path,headers=None,data=None,limit=65536):
        if not re.fullmatch(r'/api/device/backup-exports/[0-9a-f-]{36}(?:/recovery-(?:kit|input))?',path):
            raise ExportRejected('INVALID_NATIVE_PATH')
        token=self.credential()
        if not isinstance(token,str) or not token or '\n' in token or '\r' in token:raise ExportRejected('NATIVE_AUTH_UNAVAILABLE')
        request=urllib.request.Request(self.origin+path,data=data,method=method,headers={'Authorization':'Bearer '+token,**(headers or {})})
        try:
            with self.opener.open(request,timeout=90) as response:
                if response.status==204:return None
                raw=response.read(limit+1)
                if len(raw)>limit:raise ExportRejected('NATIVE_RESPONSE_OVERSIZE')
                return raw
        except urllib.error.HTTPError as err:
            if err.code in (401,403,404,410):raise ExportRejected('NATIVE_AUTH_CHANGED') from None
            raise ExportRejected('NATIVE_TRANSPORT_FAILED') from None
        except (urllib.error.URLError,TimeoutError):raise ExportRejected('NATIVE_TRANSPORT_FAILED') from None
    async def call(self,method,path,headers=None,data=None,limit=65536):
        return await asyncio.to_thread(self._request,method,path,headers,data,limit)

class PortalBackupTransport:
    def __init__(self,origin,credential):self.http=FixedTransport(origin,credential)
    def headers(self,j):return {'X-Backup-Nonce':j['nonce'],'X-Backup-Binding':j['bindingGeneration']}
    def path(self,j):return '/api/device/backup-exports/'+j['exportId']
    async def status(self,j):return json.loads(await self.http.call('GET',self.path(j),self.headers(j)))
    async def post(self,j,body):
        return json.loads(await self.http.call('POST',self.path(j),{**self.headers(j),'Content-Type':'application/json'},json.dumps(body).encode()))
    async def put(self,j,offset,data,digest):
        return json.loads(await self.http.call('PUT',self.path(j),{**self.headers(j),'Content-Type':'application/octet-stream','X-Chunk-Offset':str(offset),'X-Chunk-Sha256':digest},data))
    async def recovery_input(self,j):return await self.http.call('GET',self.path(j)+'/recovery-input',self.headers(j),limit=16384)
    async def recovery_kit(self,j,nonce,data):
        return await self.http.call('PUT',self.path(j)+'/recovery-kit',{**self.headers(j),'Content-Type':'text/plain','X-Recovery-Nonce':nonce},data)

class SupervisorBackupTransport:
    def __init__(self,credential):self.credential=credential;self.opener=urllib.request.build_opener(NoRedirect())
    def _open(self,method,path,body=None):
        if path.startswith('/backups/config') or not (method=='GET' and (path in ('/addons/self/info','/addons','/backups') or re.fullmatch(r'/backups/[A-Za-z0-9_-]{1,80}/(?:info|download)',path)) or method=='POST' and path=='/backups/new/full'):
            raise ExportRejected('INVALID_SUPERVISOR_OPERATION')
        token=self.credential()
        if not isinstance(token,str) or not token or '\n' in token or '\r' in token:raise ExportRejected('SUPERVISOR_AUTH_UNAVAILABLE')
        request=urllib.request.Request('http://supervisor'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:return self.opener.open(request,timeout=90)
        except (urllib.error.URLError,TimeoutError):raise ExportRejected('SUPERVISOR_TRANSPORT_FAILED') from None
    def _json(self,method,path,body):
        with self._open(method,path,body) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ExportRejected('SUPERVISOR_RESPONSE_OVERSIZE')
            result=json.loads(raw)
            if result.get('result')!='ok' or not isinstance(result.get('data'),dict):raise ExportRejected('SUPERVISOR_RESPONSE_INVALID')
            return result['data']
    async def json(self,method,path,body=None):return await asyncio.to_thread(self._json,method,path,body)
    async def download(self,slug):
        response=await asyncio.to_thread(self._open,'GET','/backups/'+slug+'/download')
        try:
            while True:
                chunk=await asyncio.to_thread(response.read,CHUNK_BYTES)
                if not chunk:break
                yield chunk
        finally:response.close()
