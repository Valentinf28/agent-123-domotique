"""Read Deye LP1 identity/topology and verify AC scaling using bounded read-only registers."""
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

def power_modifier(values):
    """Choose 1 W or 10 W only from a decisive same-frame AC balance.

    An idle inverter, nonzero GEN port, inconsistent CT or ambiguous balance
    never establishes a new scale. Both internal and external grid must agree.
    """
    if len(values)!=26:return None
    signed=lambda index: values[index]-65536 if values[index]>32767 else values[index]
    gen,output,load=signed(0),signed(9),signed(12)
    if gen!=0 or abs(output)<150 or load<0:return None
    tolerance=max(30,abs(output)*0.03)
    candidates=[mod for mod,scale in ((0,1),(1,10))
                if all(abs(load*scale-(output+signed(index)*scale))<=tolerance for index in (3,6))]
    return candidates[0] if len(candidates)==1 else None

def _registers(host,serial,start,count):
    if (start,count) not in ((0,22),(166,26)):raise ValueError('Lecture solaire hors périmètre.')
    seq=secrets.randbelow(254)+1;rtu=struct.pack('>BBHH',1,3,start,count);rtu+=crc(rtu)
    frame=b'\xa5'+struct.pack('<H',15+len(rtu))+b'\x10\x45'+bytes([seq,0])+struct.pack('<I',serial)+b'\x02'+bytes(14)+rtu
    frame+=bytes([sum(frame[1:])&255,0x15])
    with socket.create_connection((host,8899),timeout=2) as transport:
        transport.sendall(frame);deadline=time.monotonic()+3;reply=b''
        while len(reply)<512 and time.monotonic()<deadline:
            transport.settimeout(max(.01,deadline-time.monotonic()));part=transport.recv(512-len(reply))
            if not part:break
            reply+=part
            if len(reply)>=3 and len(reply)>=int.from_bytes(reply[1:3],'little')+13:break
    if (len(reply)<27 or len(reply)!=int.from_bytes(reply[1:3],'little')+13 or reply[0]!=0xa5
        or reply[-1]!=0x15 or reply[4]!=0x15 or reply[5]!=seq
        or int.from_bytes(reply[7:11],'little')!=serial or reply[-2]!=sum(reply[1:-2])&255):
        raise RuntimeError('Réponse solaire invalide.')
    data=reply[25:-2]
    if len(data)==count*2+7 and data[-2:]==b'\0\0':data=data[:-2]
    if len(data)!=count*2+5 or data[:3]!=bytes([1,3,count*2]) or crc(data[:-2])!=data[-2:]:
        raise RuntimeError('Réponse solaire invalide.')
    return reply,seq,struct.unpack('>'+str(count)+'H',data[3:-2])

def read(host,serial):
    try:
        frame,seq,_=_registers(host,serial,0,22)
        result=parse(frame,seq,serial)
        if result is None:raise RuntimeError('Identité solaire invalide.')
    except (OSError,RuntimeError):
        raise RuntimeError('Le nombre d’entrées solaires de cet onduleur n’a pas pu être lu. Réessayez sa connexion.') from None
    # Never infer scaling from unrelated snapshots or persist a new scale when
    # one frame is unavailable/inconclusive. Existing explicit scale survives.
    detected=[]
    for _ in range(2):
        try:detected.append(power_modifier(_registers(host,serial,166,26)[2]))
        except (OSError,RuntimeError):detected.append(None)
    result['mod']=detected[0] if detected[0] is not None and detected[0]==detected[1] else None
    return result
