"""Real private D-Bus exchange. Never connects to system bus, TTYs or host systemd."""
import asyncio,json
from pathlib import Path
import subprocess,sys,tempfile
from dbus_fast import DBusError,Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import PropertyAccess
from dbus_fast.service import ServiceInterface,method,dbus_property
sys.path.insert(0,'/opt/maintenance')
from host import Host,DEST,ROOT,UNIT
from security import generate,Attempts,Refused
from session import Session

class FakeUnit(ServiceInterface):
    def __init__(self):super().__init__(DEST+'.Unit');self.active='inactive'
    @dbus_property(access=PropertyAccess.READ)
    def ActiveState(self)->'s':return self.active

class Manager(ServiceInterface):
    def __init__(self,bus):super().__init__(DEST+'.Manager');self.bus=bus;self.unit=FakeUnit();self.starts=0;self.received=None;self.path=ROOT+'/unit/labox_fixture';bus.export(self.path,self.unit)
    @method()
    def GetUnit(self,name:'s')->'o':
        if name!=UNIT:raise DBusError(DEST+'.NoSuchUnit','Fixture unit is absent')
        return self.path
    @method()
    def StartTransientUnit(self,name:'s',mode:'s',props:'a(sv)',aux:'a(sa(sv))')->'o':
        assert name==UNIT and mode=='fail' and aux==[]
        values={k:v.value for k,v in props}
        assert values['RuntimeMaxUSec']==600_000_000
        assert values['TTYPath']=='/dev/tty8'
        assert len(values['ExecStart'])==1
        assert list(values['ExecStart'][0])==['/usr/sbin/haos-cli',['/usr/sbin/haos-cli'],False]
        assert values['Restart']=='no' and 'Environment' not in values
        self.starts+=1;self.received=values;self.unit.active='active';return ROOT+'/job/1'
    @method()
    def StopUnit(self,name:'s',mode:'s')->'o':
        assert name==UNIT and mode=='replace';self.unit.active='inactive';return ROOT+'/job/2'

async def check(address):
    server=await MessageBus(bus_address=address).connect();await server.request_name(DEST);manager=Manager(server);server.export(ROOT,manager)
    host=Host();await host.connect(address)
    try:
        identity=await host.machine_id();options,code=generate(identity)
        with tempfile.TemporaryDirectory() as tmp:
            attempts=Attempts(Path(tmp)/'attempts','fixture-boot');session=Session(options,host,attempts)
            try:await session.open('0'*24)
            except Refused:pass
            else:raise AssertionError('Unauthenticated session')
            assert manager.starts==0
            attempts.succeeded()
            result=await session.open(code,7)
            assert result['sessionStarted'] and manager.starts==1
            assert await host.state()=='active'
            await host.stop();assert await host.state()=='inactive'
            assert code not in json.dumps(manager.received)
            print(json.dumps({'passed':True,'privateBus':True,'authenticationBeforeSession':True,'hostTimeoutSeconds':manager.received['RuntimeMaxUSec']//1_000_000,'hostModified':False}))
    finally:host.bus.disconnect();server.disconnect()

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        address='unix:path='+tmp+'/test.bus'
        daemon=subprocess.Popen(['dbus-daemon','--session','--nofork','--address='+address,'--print-address=1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            actual=daemon.stdout.readline().decode().strip();assert actual.startswith(address);asyncio.run(check(actual))
        finally:daemon.terminate();daemon.wait(timeout=5)
