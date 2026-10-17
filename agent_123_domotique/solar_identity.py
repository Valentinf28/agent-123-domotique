"""Bounded SolarMAN V5 identity read (Deye registers 3–7 only).

Frame layout follows the bundled ha-solarman 25.08.16 implementation.
No write function or arbitrary register address is accepted.
"""
import secrets
import socket
import struct
import time


def crc(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xa001 if value & 1 else 0)
    return struct.pack('<H', value)


def request(serial, sequence):
    rtu = bytes.fromhex('010300030005')
    rtu += crc(rtu)
    frame = b'\xa5' + struct.pack('<H', 15 + len(rtu)) + b'\x10\x45' + bytes([sequence, 0]) + struct.pack('<I', serial)
    frame += b'\x02' + bytes(14) + rtu
    return frame + bytes([sum(frame[1:]) & 255, 0x15])


def parse(frame, sequence, serial):
    if len(frame) < 32 or frame[0] != 0xa5 or frame[-1] != 0x15:
        return None
    if len(frame) != int.from_bytes(frame[1:3], 'little') + 13:
        return None
    actual = int.from_bytes(frame[7:11], 'little')
    if not actual or (serial and actual != serial) or frame[4] != 0x15 or frame[5] != sequence:
        return None
    if frame[-2] != sum(frame[1:-2]) & 255:
        return None
    rtu = frame[25:-2]
    if len(rtu) == 17 and rtu[-2:] == b'\0\0':
        rtu = rtu[:-2]
    if len(rtu) != 15 or rtu[:3] != b'\x01\x03\x0a' or crc(rtu[:-2]) != rtu[-2:]:
        return None
    try:
        inverter = rtu[3:13].decode('ascii')
    except UnicodeError:
        return None
    if not inverter.isalnum():
        return None
    return {'loggerSerial': actual, 'inverterSerial': inverter}


def identify(host, serial=0):
    """Called only for LAN candidates with port 8899; never sends credentials."""
    sequence = secrets.randbelow(254) + 1
    try:
        with socket.create_connection((host, 8899), timeout=1) as transport:
            transport.sendall(request(serial, sequence))
            deadline = time.monotonic() + 2
            frame = b''
            while len(frame) < 1024 and time.monotonic() < deadline:
                transport.settimeout(max(.01, deadline-time.monotonic()))
                part = transport.recv(1024-len(frame))
                if not part:
                    return None
                frame += part
                if len(frame) >= 3 and len(frame) >= int.from_bytes(frame[1:3], 'little') + 13:
                    return parse(frame, sequence, serial)
    except OSError:
        pass
    return None
