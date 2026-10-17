"""Read Deye LP1 device identity and MPPT count (holding registers 0–21 only)."""
import secrets,socket,struct,time
from solar_identity import crc

def parse(frame,sequence,serial):
    if (len(frame)<27 or len(frame)!=int.from_bytes(frame[1:3],'little')+13 or frame[0]!=0xa5
        or frame[-1]!=0x15 or frame[4]!=0x15 or frame[5]!=sequence
        or int.from_bytes(frame[7:11],'little')!=serial or frame[-2]!=sum(frame[1:-2])&255):return None
    rtu=frame[25:-2]
    if len(rtu)==51 and rtu[-2:]==b'\0\0':rtu=rtu[:-2]
    if len(rtu)!=49 or rtu[:3]!=b'\x01\x03\x2c' or crc(rtu[:-2])!=rtu[-2:]:return None
    values=struct.unpack('>22H',rtu[3:-2])
    mppt=(values[18]&0x0f00)>>8;phases=values[18]&0x000f
    try:identity=rtu[9:19].decode('ascii')
    except UnicodeError:return None
    if values[0] not in (3,768) or not 1<=mppt<=4 or phases!=1 or not identity.isalnum():return None
    return {'loggerSerial':serial,'inverterSerial':identity,'mppt':mppt,'phase':phases,'mod':0}

def read(host,serial):
    seq=secrets.randbelow(254)+1;rtu=bytes.fromhex('010300000016');rtu+=crc(rtu)
    frame=b'\xa5'+struct.pack('<H',15+len(rtu))+b'\x10\x45'+bytes([seq,0])+struct.pack('<I',serial)+b'\x02'+bytes(14)+rtu
    frame+=bytes([sum(frame[1:])&255,0x15])
    try:
        with socket.create_connection((host,8899),timeout=2) as transport:
            transport.sendall(frame);deadline=time.monotonic()+3;reply=b''
            while len(reply)<512 and time.monotonic()<deadline:
                transport.settimeout(max(.01,deadline-time.monotonic()));part=transport.recv(512-len(reply))
                if not part:break
                reply+=part
                if len(reply)>=3 and len(reply)>=int.from_bytes(reply[1:3],'little')+13:
                    if result:=parse(reply,seq,serial):return result
                    break
    except OSError:pass
    raise RuntimeError('Le nombre d’entrées solaires de cet onduleur n’a pas pu être lu. Réessayez sa connexion.')
