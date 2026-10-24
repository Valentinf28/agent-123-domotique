"""Reads ONLY tty8 while active. Never opens evdev devices or observes app input."""
import asyncio
import fcntl
import os
import struct
import termios
import time
import json
from pathlib import Path
from security import save
from security import Refused

VT_GETSTATE=0x5603

class Terminal:
    def __init__(self,identity,boot_id):
        self.fd=None;self.monitor=None;self.original=None;self.return_vt=1
        self.claim={"machine":identity,"boot":boot_id};self.claim_path=Path("/data/tty8-reservation.json")
    def active(self):
        raw=fcntl.ioctl(self.monitor,VT_GETSTATE,bytes(6));return struct.unpack('HHH',raw)[0]
    def open(self):
        if self.monitor is None:self.monitor=os.open('/dev/tty0',os.O_RDONLY|os.O_NOCTTY|os.O_CLOEXEC)
        # Refuse to replace an already selected/occupied native tty8.
        state=struct.unpack('HHH',fcntl.ioctl(self.monitor,VT_GETSTATE,bytes(6)))
        previous=json.loads(self.claim_path.read_text()) if self.claim_path.exists() else None
        if state[2] & (1 << 8) and previous!=self.claim:raise Refused('console_technique_occupee')
        self.fd=os.open('/dev/tty8',os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK|os.O_CLOEXEC)
        if struct.unpack("i",fcntl.ioctl(self.fd,0x4B3B,bytes(4)))[0]!=0:raise Refused("console_graphique_occupee")
        self.original=termios.tcgetattr(self.fd)
        save(self.claim_path,self.claim)
    def write(self,text):os.write(self.fd,text.encode('utf-8'))
    def clear(self):self.write('\033[2J\033[H')
    def prompt(self):
        settings=termios.tcgetattr(self.fd)
        settings[3] &= ~(termios.ECHO|termios.ICANON|termios.ISIG)
        settings[6][termios.VMIN]=0;settings[6][termios.VTIME]=0
        termios.tcsetattr(self.fd,termios.TCSANOW,settings);termios.tcflush(self.fd,termios.TCIFLUSH)
        self.clear();self.write('1.2.3 Home - Maintenance technique\r\n\r\nCode technicien de cette box : ')
    async def read_code(self):
        data=bytearray();started=time.monotonic()
        while time.monotonic()-started<60:
            if self.active()!=8:
                data.clear();return None
            try:chunk=os.read(self.fd,1)
            except BlockingIOError:chunk=b''
            if chunk in (b'\r',b'\n'):
                self.write('\r\n');return data.decode('ascii',errors='ignore')
            if chunk in (b'\x03',b'\x04',b'\x1b'):data.clear();return None
            if chunk in (b'\x7f',b'\x08'):
                if data:data.pop();self.write('\b \b')
            elif chunk:
                if len(data)>=40:data.clear();return None
                if chunk in b'0123456789- ':data.extend(chunk);self.write('*')
            await asyncio.sleep(.03)
        data.clear();return None
    def release_for_session(self):
        if self.original is None or self.fd is None:return
        termios.tcsetattr(self.fd,termios.TCSANOW,self.original);termios.tcflush(self.fd,termios.TCIFLUSH)
    def handoff(self):
        self.release_for_session()
        if self.fd is not None:os.close(self.fd);self.fd=None
        self.original=None
    def close(self):
        if self.fd is not None:
            try:
                if self.original is not None:self.release_for_session();self.clear()
            finally:os.close(self.fd);self.fd=None
        if self.monitor is not None:os.close(self.monitor);self.monitor=None
