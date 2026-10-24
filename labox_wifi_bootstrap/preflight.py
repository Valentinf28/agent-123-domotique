"""Read-only workshop capability report. Does not activate/scan/configure any interface."""
import asyncio
import json
from pathlib import Path
from model import read
from network import DEV, WIFI, DEST, ROOT, Network

async def main():
    net=Network(); await net.connect()
    try:
        root=await net.props(ROOT,DEST)
        radios=[]
        for path in (await net.call(ROOT,DEST,'GetDevices'))[0]:
            device=await net.props(path,DEV)
            if device['DeviceType'] != 2:continue
            wifi=await net.props(path,WIFI)
            caps=wifi['WirelessCapabilities']
            radios.append({'interface':device['Interface'],'permanentMac':wifi.get('PermHwAddress',''),
                'managed':device.get('Managed',False),'apAdvertised':bool(caps & 0x40),
                'wpa2AesAdvertised':caps & 0x28 == 0x28})
        marker=read('/homeassistant_config/.labox-network-bootstrap.json')
        print(json.dumps({'networkManager':root['Version'],'wirelessEnabled':root['WirelessEnabled'],
            'radios':radios,'factoryContext':marker.get('factoryContext'),
            'prepared':marker.get('prepared') is True,'installed':marker.get('installed') is True,
            'networkModified':False,'hardwareQualified':False},indent=2))
    finally:net.bus.disconnect()

if __name__=='__main__':asyncio.run(main())
