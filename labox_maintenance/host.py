"""Exact transient HAOS session on tty8, no arbitrary unit, command or environment."""
import asyncio
from dbus_fast import Message,MessageType,Variant
from dbus_fast.aio import MessageBus
from security import Refused

DEST='org.freedesktop.systemd1';ROOT='/org/freedesktop/systemd1';UNIT='labox-maintenance-session.service'
MAX_SESSION=600

def properties(return_vt=1):
    if type(return_vt) is not int or not 1 <= return_vt <= 7:raise Refused("console_retour_invalide")
    return [(key,Variant(signature,value)) for key,signature,value in [
        ('Description','s','La Box - session de maintenance locale'),('Type','s','simple'),
        ('ExecStart','a(sasb)',[['/usr/sbin/haos-cli',['/usr/sbin/haos-cli'],False]]),
        ('ExecStopPost','a(sasb)',[['/usr/bin/chvt',['/usr/bin/chvt',str(return_vt)],True]]),
        ('StandardInput','s','tty-force'),('StandardOutput','s','tty'),('StandardError','s','tty'),
        ('TTYPath','s','/dev/tty8'),('TTYReset','b',True),('TTYVHangup','b',True),('TTYVTDisallocate','b',True),
        ('RuntimeMaxUSec','t',MAX_SESSION*1_000_000),('TimeoutStopUSec','t',3_000_000),
        ('KillMode','s','control-group'),('SendSIGHUP','b',True),('Restart','s','no'),
        ('CollectMode','s','inactive-or-failed')]]

class Host:
    def __init__(self):self.bus=None;self.destination=DEST
    async def connect(self,address='unix:path=/run/dbus/system_bus_socket'):
        self.bus=await MessageBus(bus_address=address).connect()
        reply=await self.bus.call(Message(destination='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='GetNameOwner',signature='s',body=[DEST]))
        if reply.message_type==MessageType.ERROR:raise Refused('gestionnaire_systeme_indisponible')
        self.destination=reply.body[0]
    async def call(self,member,signature='',body=None,path=ROOT,interface=DEST+'.Manager',missing=False):
        reply=await asyncio.wait_for(self.bus.call(Message(destination=self.destination,path=path,interface=interface,member=member,signature=signature,body=body or [])),8)
        if reply.message_type==MessageType.ERROR:
            if missing and reply.error_name=='org.freedesktop.systemd1.NoSuchUnit':return None
            raise Refused('session_technique_indisponible')
        return reply.body
    async def machine_id(self):
        return (await self.call('GetMachineId',path=ROOT,interface='org.freedesktop.DBus.Peer'))[0]
    async def state(self,unit=UNIT):
        result=await self.call('GetUnit','s',[unit],missing=True)
        if result is None:return 'inactive'
        values=await self.call('GetAll','s',[DEST+'.Unit'],path=result[0],interface='org.freedesktop.DBus.Properties')
        return values[0]['ActiveState'].value
    async def masked(self,unit):
        if unit not in ('getty@tty8.service','autovt@tty8.service','ha-cli@tty8.service'):
            raise Refused('unite_non_autorisee')
        path=(await self.call('LoadUnit','s',[unit]))[0]
        values=await self.call('GetAll','s',[DEST+'.Unit'],path=path,interface='org.freedesktop.DBus.Properties')
        return values[0].get('LoadState',Variant('s','unknown')).value=='masked'
    async def start(self,return_vt=1):
        if await self.state() not in ('inactive','failed'):raise Refused('session_deja_ouverte')
        for unit in ('ha-cli@tty8.service','getty@tty8.service'):
            if await self.state(unit) not in ('inactive','failed'):raise Refused('console_technique_occupee')
        await self.call('StartTransientUnit','ssa(sv)a(sa(sv))',[UNIT,'fail',properties(return_vt),[]])
    async def stop(self):
        if await self.state() not in ('inactive','failed'):
            await self.call('StopUnit','ss',[UNIT,'replace'])
