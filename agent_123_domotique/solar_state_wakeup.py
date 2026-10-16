"""Read-only HA events wake the existing durable heartbeat, never a device action."""
import json
import re
import time


def solar_entities(registry):
    if isinstance(registry, dict):registry=registry.get('result')
    if not isinstance(registry, list):return set()
    return {r['entity_id'] for r in registry if isinstance(r, dict)
            and r.get('platform') in ('solarman','labox_ddzy422') and not r.get('disabled_by')
            and isinstance(r.get('entity_id'),str) and re.fullmatch(r'sensor\.[a-z0-9_]+',r['entity_id'])}


def watch_session(socket, token, entities, wake, *, clock=time.monotonic, stop=None):
    if json.loads(socket.recv()).get('type')!='auth_required':raise RuntimeError('Authentication required')
    socket.send(json.dumps({'type':'auth','access_token':token}))
    if json.loads(socket.recv()).get('type')!='auth_ok':raise RuntimeError('Authentication refused')
    socket.send(json.dumps({'id':1,'type':'subscribe_events','event_type':'state_changed'}))
    deadline=clock()+60;last_wake=-float('inf')
    while (stop is None or not stop.is_set()) and clock()<deadline:
        message=json.loads(socket.recv())
        if message.get('type')=='result' and message.get('id')==1 and message.get('success') is not True:
            raise RuntimeError('Subscription refused')
        if message.get('type')!='event' or message.get('id')!=1:continue
        event=message.get('event',{})
        if event.get('event_type')!='state_changed':continue
        data=event.get('data',{});old,new=data.get('old_state'),data.get('new_state')
        if data.get('entity_id') not in entities or not isinstance(new,dict):continue
        if new.get('attributes',{}).get('device_class')!='power':continue
        if isinstance(old,dict) and old.get('state')==new.get('state'):continue
        now=clock()
        # Simultaneous phase/production updates coalesce; periodic heartbeat is fallback.
        if now-last_wake>=1:
            wake.set();last_wake=now


def watch_forever(token, wake, registry, connect, *, stop=None):
    import threading
    stop=stop or threading.Event();delay=2
    while not stop.is_set():
        socket=None
        try:
            entities=solar_entities(registry())
            if not entities:
                stop.wait(30);continue
            socket=connect('ws://supervisor/core/websocket',timeout=30)
            watch_session(socket,token,entities,wake,stop=stop);delay=2
        except Exception:
            # No state, device address or credential is logged. Normal heartbeat continues.
            pass
        finally:
            if socket:socket.close()
        stop.wait(delay);delay=min(30,delay*2)
