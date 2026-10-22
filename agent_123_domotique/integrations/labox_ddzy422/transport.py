"""Read-only DDZY422-D2 AT transport; protocol reference: github.com/Pengo-fmm/ddzy422-local.
Only documented FC03 measurement blocks; no configuration or register writes.
"""
import socket,struct,time,ipaddress,datetime,re,math,threading
from pathlib import Path

def crc16(data):
 crc=0xffff
 for byte in data:
  crc ^= byte
  for _ in range(8):crc=(crc>>1)^0xa001 if crc&1 else crc>>1
 return struct.pack('<H',crc)
def signed_magnitude(value,bits):return -(value&((1<<(bits-1))-1)) if value&(1<<(bits-1)) else value
class Meter:
 def __init__(self,host,serial,mac):
  validate_settings(host,serial,mac)
  self.addr=(host,48899);self.serial=serial;self.mac=mac.replace(':','').upper();self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.stats={'requests':0,'invalidFrames':0,'timeouts':0,'retries':0}
 def enter(self):
  for attempt in range(2):
   self.sock.settimeout(2);self.sock.sendto(b'WIFIKIT-214028-READ',self.addr)
   try:data,peer=self.sock.recvfrom(1024)
   except socket.timeout:continue
   if peer!=self.addr:raise ValueError('Wrong discovery source')
   fields=data.decode('ascii').strip().split(',')
   if fields!=[self.addr[0],self.mac,str(self.serial)]:raise ValueError('Wrong meter identity')
   self.sock.sendto(b'+ok',self.addr);time.sleep(.4);return
  raise TimeoutError('Meter discovery handshake did not answer')
 def read(self,start,count,tries=2):
  if (start,count) not in [(0,14),(14,20)]:raise ValueError('Only documented measurement reads allowed')
  body=struct.pack('>BBHH',1,3,start,count);rtu=body+crc16(body)
  request=b'AT+INVDATA='+str(len(rtu)).encode()+b','+rtu.hex().encode()+b'\n'
  for attempt in range(tries):
   self.sock.settimeout(.1);drain_until=time.monotonic()+.3
   while time.monotonic()<drain_until:
    try:self.sock.recvfrom(4096)
    except socket.timeout:break
   self.sock.sendto(request,self.addr);self.stats['requests']+=1;self.stats['retries']+=int(attempt>0);deadline=time.monotonic()+2
   while time.monotonic()<deadline:
    self.sock.settimeout(max(.01,deadline-time.monotonic()))
    try:data,peer=self.sock.recvfrom(4096)
    except socket.timeout:self.stats['timeouts']+=1;break
    if peer!=self.addr or not data.startswith(b'+ok='):continue
    try:raw=bytes.fromhex(data[4:].replace(b'\x10',b'').strip().decode('ascii'))
    except (ValueError,UnicodeError):continue
    if len(raw)!=5+2*count or raw[:3]!=bytes([1,3,2*count]) or crc16(raw[:-2])!=raw[-2:]:self.stats['invalidFrames']+=1;continue
    return list(struct.unpack('>'+'H'*count,raw[3:-2]))
   time.sleep(.4)
  raise TimeoutError('No valid CRC-checked measurement block')
 def close(self):self.sock.close()
 def sample(self):
  var=self.read(0,14);eng=self.read(14,20)
  def pair(rows,index):return rows[index]<<16|rows[index+1]
  values={'voltageV':var[1]/10,'currentA':signed_magnitude(pair(var,2),32)/1000,'gridPowerW':signed_magnitude(pair(var,6),32),'powerFactor':signed_magnitude(var[12],16)/1000,'frequencyHz':var[13]/100,'importTotalKwh':pair(eng,0)/100,'exportTotalKwh':pair(eng,10)/100}
  if not (80<values['voltageV']<300 and 40<values['frequencyHz']<70 and abs(values['powerFactor'])<=1.05):raise ValueError('Implausible meter values')
  if not (abs(values['gridPowerW'])<=25000 and abs(values['currentA'])<=120):raise ValueError('Outside this single-phase meter range')
  return {'readAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'values':values,'rawInstantaneous':var,'rawEnergy':eng,'crcVerified':True,'identityVerified':True,'statistics':dict(self.stats)}

PRIVATE_NETWORKS = tuple(ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))

def validate_settings(host,serial,mac):
    ip=ipaddress.IPv4Address(host)
    if not any(ip in n for n in PRIVATE_NETWORKS):raise ValueError('A private IPv4 meter address is required')
    if type(serial) is not int or not 0 < serial <= 0xffffffff:raise ValueError('Invalid meter serial')
    compact=mac.replace(':','').upper() if isinstance(mac,str) else ''
    if not re.fullmatch('[0-9A-F]{12}',compact) or compact=='000000000000' or int(compact[:2],16)&1:raise ValueError('Invalid unicast meter MAC')
    return {'host':str(ip),'logger_serial':serial,'mac':compact}

def validate_local_host(host,adapters):
    ip=ipaddress.IPv4Address(host)
    for adapter in adapters:
        if not adapter.get('enabled'):continue
        for row in adapter.get('ipv4',[]):
            try:interface=ipaddress.IPv4Interface(f"{row['address']}/{row['network_prefix']}")
            except (KeyError,ValueError,TypeError):continue
            if ip in interface.network and ip not in (interface.ip,interface.network.network_address,interface.network.broadcast_address):return
    raise ValueError('Meter must be on a local network of this box')

_CLIENT_LOCKS = {}

def read_sample(settings):
    # A cancelled HA await cannot cancel an executor thread. This thread lock
    # keeps a reload/new flow from opening a second client while it finishes.
    lock = _CLIENT_LOCKS.setdefault(settings['logger_serial'], threading.Lock())
    if not lock.acquire(timeout=20):raise TimeoutError('Meter reader busy')
    meter = None
    try:
        meter=Meter(settings['host'],settings['logger_serial'],settings['mac'])
        meter.enter()
        sample=meter.sample()
        return {'values':sample['values'],'readAtUtc':sample['readAtUtc']}
    finally:
        if meter:meter.close()
        lock.release()

class IndexGuard:
    """Persisted physical counter continuity; no guessed offsets or reset-to-zero."""
    def __init__(self,previous=None):self.previous=previous
    def validate(self,values,at):
        keys=('importTotalKwh','exportTotalKwh')
        if not all(isinstance(values.get(k),(int,float)) and math.isfinite(values[k]) and values[k]>=0 for k in keys):raise ValueError('Invalid energy indexes')
        if not isinstance(at,(int,float)) or not math.isfinite(at):raise ValueError('Invalid observation time')
        if self.previous is not None:
            if not isinstance(self.previous,dict) or not all(isinstance(self.previous.get(k),(int,float)) and math.isfinite(self.previous[k]) and self.previous[k]>=0 for k in (*keys,'at')):raise ValueError('Persisted energy checkpoint invalid')
            elapsed=at-self.previous['at']
            if elapsed < 0:raise ValueError('Clock moved backwards')
            bound=.03+25*elapsed/3600
            for key in keys:
                delta=values[key]-self.previous[key]
                if delta < -0.000001:raise ValueError('Energy index decreased; explicit maintenance required')
                if delta > bound:raise ValueError('Energy index jump exceeds single-phase meter range')
        self.previous={**{k:values[k] for k in keys},'at':at}
        return dict(self.previous)
