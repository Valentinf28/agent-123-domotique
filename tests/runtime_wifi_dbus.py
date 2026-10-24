"""Wire-level test on a PRIVATE D-Bus daemon. Never connects to a host bus or radio."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from dbus_fast import Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import PropertyAccess
from dbus_fast.service import ServiceInterface, method, dbus_property

sys.path.insert(0, '/opt/wifi')
from network import Network, ROOT, DEST, DEV, WIFI, CONN, ACTIVE, SETTINGS
from model import Lifecycle
from controller import Controller

DEVICE=ROOT+'/Devices/1'; IPCONFIG=ROOT+'/IP4Config/1'; ACTIVE_PATH=ROOT+'/ActiveConnection/1'
READ=PropertyAccess.READ

class Manager(ServiceInterface):
    def __init__(self, bus):
        super().__init__(DEST);self.bus=bus;self.connections={};self.checkpoints={};self.current='/'
        self.counter=0;self.checkpoint_calls=[];self.rollback_count=0
    @method()
    def GetDevices(self) -> 'ao':return [DEVICE]
    @method()
    def ActivateConnection(self,connection:'o',device:'o',specific:'o')->'o':
        assert device==DEVICE and specific=='/'
        assert connection in self.connections
        self.current=connection;return ACTIVE_PATH
    @method()
    def CheckpointCreate(self,devices:'ao',timeout:'u',flags:'u')->'o':
        assert devices==[DEVICE] and timeout>0 and flags in (0,8)
        assert flags or not self.checkpoints
        self.counter+=1;p=ROOT+'/Checkpoint/'+str(self.counter)
        self.checkpoints[p]=self.current;self.bus.export(p,Checkpoint());self.checkpoint_calls.append([timeout,flags]);return p
    @method()
    def CheckpointDestroy(self,checkpoint:'o'):
        del self.checkpoints[checkpoint];self.bus.unexport(checkpoint)
    @method()
    def CheckpointRollback(self,checkpoint:'o')->'a{su}':
        self.current=self.checkpoints[checkpoint];del self.checkpoints[checkpoint]
        self.bus.unexport(checkpoint);self.rollback_count+=1;return {DEVICE:0}
    @dbus_property(access=READ)
    def WirelessEnabled(self)->'b':return True
    @dbus_property(access=READ)
    def WirelessHardwareEnabled(self)->'b':return True
    @dbus_property(access=READ)
    def Checkpoints(self)->'ao':return list(self.checkpoints)

class Checkpoint(ServiceInterface):
    def __init__(self):super().__init__(DEST+'.Checkpoint')
    @dbus_property(access=READ)
    def Devices(self)->'ao':return [DEVICE]

class Connection(ServiceInterface):
    def __init__(self,owner,path,settings):super().__init__(CONN);self.owner=owner;self.path=path;self.settings=settings;self.saved=False
    @method()
    def GetSettings(self)->'a{sa{sv}}':
        data=deepcopy(self.settings);data.get('802-11-wireless-security',{}).pop('psk',None);return data
    @method()
    def Delete(self):
        self.owner.connections.pop(self.path);self.owner.bus.unexport(self.path)
        if self.owner.current==self.path:self.owner.current='/'
    @method()
    def Update2(self,settings:'a{sa{sv}}',flags:'u',args:'a{sv}')->'a{sv}':
        assert flags==1 and not args
        assert settings['connection']['autoconnect'].value
        self.settings=settings;self.saved=True;return {}

class Settings(ServiceInterface):
    def __init__(self,owner):super().__init__(DEST+'.Settings');self.owner=owner
    @method()
    def ListConnections(self)->'ao':return list(self.owner.connections)
    @method()
    def AddConnection2(self,settings:'a{sa{sv}}',flags:'u',args:'a{sv}')->'oa{sv}':
        assert flags==2 and args=={}
        assert not settings['connection']['autoconnect'].value
        assert settings['802-11-wireless-security']['proto'].value==['rsn']
        self.owner.counter+=1;p=SETTINGS+'/'+str(self.owner.counter)
        c=Connection(self.owner,p,settings);self.owner.connections[p]=c;self.owner.bus.export(p,c);return [p,{}]

class Device(ServiceInterface):
    def __init__(self,owner):super().__init__(DEV);self.owner=owner
    @dbus_property(access=READ)
    def DeviceType(self)->'u':return 2
    @dbus_property(access=READ)
    def Managed(self)->'b':return True
    @dbus_property(access=READ)
    def Interface(self)->'s':return 'fixture0'
    @dbus_property(access=READ)
    def State(self)->'u':return 100 if self.owner.current!='/' else 30
    @dbus_property(access=READ)
    def ActiveConnection(self)->'o':return ACTIVE_PATH if self.owner.current!='/' else '/'
    @dbus_property(access=READ)
    def Ip4Config(self)->'o':return IPCONFIG if self.owner.current!='/' else '/'

class Wireless(ServiceInterface):
    def __init__(self):super().__init__(WIFI);self.scanned=0
    @dbus_property(access=READ)
    def PermHwAddress(self)->'s':return '00:11:22:33:44:55'
    @dbus_property(access=READ)
    def WirelessCapabilities(self)->'u':return 0x268
    @dbus_property(access=READ)
    def LastScan(self)->'x':return self.scanned
    @method()
    def RequestScan(self,options:'a{sv}'):self.scanned+=1
    @method()
    def GetAllAccessPoints(self)->'ao':return []

class Active(ServiceInterface):
    def __init__(self,owner):super().__init__(ACTIVE);self.owner=owner
    @dbus_property(access=READ)
    def Uuid(self)->'s':return self.owner.connections[self.owner.current].settings['connection']['uuid'].value if self.owner.current!='/' else ''

class IPConfig(ServiceInterface):
    def __init__(self,owner):super().__init__(DEST+'.IP4Config');self.owner=owner
    def hotspot(self):return self.owner.current!='/' and self.owner.connections[self.owner.current].settings['802-11-wireless']['mode'].value=='ap'
    @dbus_property(access=READ)
    def AddressData(self)->'aa{sv}':return [{'address':Variant('s','192.168.77.1' if self.hotspot() else '192.168.99.20'),'prefix':Variant('u',24)}]
    @dbus_property(access=READ)
    def Gateway(self)->'s':return '' if self.hotspot() else '192.168.99.1'

async def check(address):
    server=await MessageBus(bus_address=address).connect();await server.request_name(DEST)
    manager=Manager(server)
    for path,iface in [(ROOT,manager),(SETTINGS,Settings(manager)),(DEVICE,Device(manager)),(DEVICE,Wireless()),(IPCONFIG,IPConfig(manager)),(ACTIVE_PATH,Active(manager))]:server.export(path,iface)
    client=Network();await client.connect(address)
    try:
        await client.select('00:11:22:33:44:55')
        with tempfile.TemporaryDirectory() as tmp:
            options={'armed':True,'factory_context':'a'*64,'wifi_mac':'00:11:22:33:44:55'}
            marker={'version':1,'factoryContext':'a'*64,'prepared':True,'installed':False}
            life=Lifecycle(Path(tmp)/'state.json');life.prepare(options,marker)
            controller=Controller(life,client,lambda:marker,options,probe=lambda _:False)
            assert await controller.open_ap()
            controller.reserve('customer-fixture','fixture-password')
            await controller.attempt('customer-fixture','fixture-password')
            assert life.data['phase']=='hotspot' and life.data['error']=='internet_non_confirme'
            assert manager.rollback_count==1 and len(manager.connections)==1
            controller.probe=lambda _:True
            controller.reserve('customer-fixture','fixture-password')
            await controller.attempt('customer-fixture','fixture-password')
            assert life.data['phase']=='complete' and life.data['provisioned']
            assert not manager.checkpoints
            await controller.close()
            assert len(manager.connections)==1 and next(iter(manager.connections.values())).saved
            assert manager.checkpoint_calls[0][1]==0
            assert manager.checkpoint_calls[1:]==[[150,8],[150,8]]
            assert 'fixture-password' not in life.path.read_text()
            print(json.dumps({'passed':True,'privateBus':True,'realDbusRoundTrips':True,'rollbackThenSuccess':True,'hostNetworkChanged':False}))
    finally:
        client.bus.disconnect();server.disconnect()

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        address='unix:path='+tmp+'/test.bus'
        daemon=subprocess.Popen(['dbus-daemon','--session','--nofork','--address='+address,'--print-address=1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            actual=daemon.stdout.readline().decode().strip()
            assert actual.startswith(address)
            asyncio.run(check(actual))
        finally:daemon.terminate();daemon.wait(timeout=5)
