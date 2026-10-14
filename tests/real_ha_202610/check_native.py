"""Real HA 2026.10.1 import/configflow/sensor/coordinator recipe, no hardware IO.

Run in the dedicated Docker image with --network none and this candidate as a
read-only bind mount. No production config, credentials, supervisor or box access.
"""
import asyncio
from datetime import datetime,timezone,timedelta
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import AsyncMock,patch

DOMAIN='labox_ddzy422'
SOURCE=Path(__file__).resolve().parents[2]/'agent_123_domotique/integrations'/DOMAIN

async def recipe():
    assert os.environ.get('LABOX_REAL_HA_ISOLATED')=='1','Dedicated isolated runtime required'
    assert not os.environ.get('SUPERVISOR_TOKEN'),'No production supervisor token permitted'
    assert sys.version_info >= (3,14,2)
    assert importlib.metadata.version('homeassistant')=='2026.10.1'
    from homeassistant.core import HomeAssistant
    from homeassistant import bootstrap,loader
    from homeassistant.components import network
    from homeassistant.helpers import entity_registry
    from homeassistant.helpers.update_coordinator import UpdateFailed
    checks=[]
    with tempfile.TemporaryDirectory(prefix='labox-real-ha-') as directory:
        target=Path(directory)/'custom_components'/DOMAIN
        target.parent.mkdir();shutil.copytree(SOURCE,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        hass=HomeAssistant(directory);hass.config.skip_pip=True;loader.async_setup(hass)
        configured=False
        try:
            result=await bootstrap.async_from_config_dict({'homeassistant':{
                'name':'La Box isolated recipe','latitude':0,'longitude':0,'elevation':0,
                'unit_system':'metric','time_zone':'UTC','country':'FR'},'sensor':{},'network':{}},hass)
            assert result is hass,'Core bootstrap failed'
            integration=await loader.async_get_integration(hass,DOMAIN)
            assert integration.domain==DOMAIN and integration.manifest['version']=='0.1.0'
            component=await integration.async_get_component()
            sensor=await integration.async_get_platform('sensor')
            coordinator_module=importlib.import_module(f'custom_components.{DOMAIN}.coordinator')
            flow_module=importlib.import_module(f'custom_components.{DOMAIN}.config_flow')
            transport=importlib.import_module(f'custom_components.{DOMAIN}.transport')
            checks.append('real_manifest_component_configflow_sensor_coordinator_import')
            settings={'host':'192.168.6.194','logger_serial':2616442643,'mac':'D42787012CD2'}
            adapters=[{'enabled':True,'ipv4':[{'address':'192.168.6.180','network_prefix':24}]}]
            def sample():
                return {'readAtUtc':datetime.now(timezone.utc).isoformat(),'values':{
                    'gridPowerW':-459,'importTotalKwh':3083.61,'exportTotalKwh':5667.90,
                    'voltageV':238.3,'currentA':-3.231,'frequencyHz':49.97,'powerFactor':-.596}}
            async def read(*args):return sample()
            with (patch.object(network,'async_get_adapters',AsyncMock(return_value=adapters)),
                  patch.object(component,'async_read',side_effect=read),
                  patch.object(flow_module,'async_read',side_effect=read),
                  patch.object(transport,'read_sample',side_effect=AssertionError('HARDWARE IO FORBIDDEN')),
                  patch.object(component,'read_sample',side_effect=AssertionError('HARDWARE IO FORBIDDEN'))):
                form=await hass.config_entries.flow.async_init(DOMAIN,context={'source':'user'})
                assert form['type']=='form' and form['step_id']=='user'
                created=await hass.config_entries.flow.async_configure(form['flow_id'],settings)
                assert created['type']=='create_entry',created
                entry=created['result'];configured=True
                await hass.async_block_till_done()
                if str(entry.state.value)!='loaded':
                    assert await hass.config_entries.async_setup(entry.entry_id)
                    await hass.async_block_till_done()
                assert str(entry.state.value)=='loaded',entry.state
                checks.append('real_native_configflow_and_entry_setup')
                registry=entity_registry.async_get(hass)
                entities={item.unique_id:item.entity_id for item in registry.entities.values() if item.config_entry_id==entry.entry_id}
                assert len(entities)==9,entities
                def entity(key):return entities[f'{DOMAIN}_2616442643_{key}']
                grid=hass.states.get(entity('gridPowerW'));export=hass.states.get(entity('exportPowerW'))
                assert float(grid.state)==-459 and float(export.state)==459,(grid,export)
                index=hass.states.get(entity('importTotalKwh'))
                assert index.attributes['device_class']=='energy' and index.attributes['state_class']=='total_increasing'
                checks.append('nine_real_sensor_entities_negative_grid_energy_semantics')
                coordinator=entry.runtime_data
                assert coordinator.guard.previous['exportTotalKwh']==5667.90
                duplicate=await hass.config_entries.flow.async_init(DOMAIN,context={'source':'user'},data=settings)
                assert duplicate['type']=='abort' and duplicate['reason']=='already_configured',duplicate
                checks.append('real_duplicate_configflow_no_second_device')
                with patch.object(component,'async_read',AsyncMock(side_effect=TimeoutError('test outage'))):
                    await coordinator.async_refresh();await hass.async_block_till_done()
                assert hass.states.get(entity('gridPowerW')).state=='unavailable'
                checks.append('real_coordinator_outage_is_unavailable_not_zero')
                await coordinator.async_refresh();await hass.async_block_till_done()
                assert float(hass.states.get(entity('gridPowerW')).state)==-459
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert entry.runtime_data.guard.previous['exportTotalKwh']==5667.90
                after={item.unique_id:item.entity_id for item in registry.entities.values() if item.config_entry_id==entry.entry_id}
                assert after==entities
                checks.append('real_reload_stable_ids_persisted_indexes')
                async def reset_counter(*args):
                    value=sample();value['values']['importTotalKwh']=0;return value
                with patch.object(component,'async_read',side_effect=reset_counter):
                    await entry.runtime_data.async_refresh();await hass.async_block_till_done()
                assert hass.states.get(entity('importTotalKwh')).state=='unavailable'
                checks.append('real_counter_decrease_fail_closed')
            print(json.dumps({'homeassistant':'2026.10.1','checks':checks,'passed':True,'hardwareReads':0,'hardwareWrites':0,'network':'must_run_with_docker_network_none'},indent=2),flush=True)
        finally:
            if configured:
                for entry in hass.config_entries.async_entries(DOMAIN):
                    try:await hass.config_entries.async_unload(entry.entry_id)
                    except Exception:pass
            await hass.async_stop()

asyncio.run(recipe())
