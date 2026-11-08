"""Read-only host identity and reserved-session check; does not touch any terminal."""
import asyncio,json
from host import Host

async def main():
    host=Host();await host.connect()
    try:
        print(json.dumps({'machineId':await host.machine_id(),
            'nativeSession':await host.state(),'tty8Gettty':await host.state('getty@tty8.service'),
            'tty8HaCli':await host.state('ha-cli@tty8.service'),
            'ordinaryConsolesMasked':{unit:await host.masked(unit) for unit in ('getty@tty8.service','autovt@tty8.service','ha-cli@tty8.service')},
            'hostModified':False,'hardwareValidated':False}))
    finally:host.bus.disconnect()

if __name__=='__main__':asyncio.run(main())
