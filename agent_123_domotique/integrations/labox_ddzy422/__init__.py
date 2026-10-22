"""Native HA entities for the identity-verified read-only local meter."""
import asyncio
from homeassistant.const import Platform
from .const import DOMAIN
from .coordinator import MeterCoordinator
from .transport import read_sample

PLATFORMS = [Platform.SENSOR]

async def async_read(hass, settings):
    locks = hass.data.setdefault(DOMAIN + '_locks', {})
    lock = locks.setdefault(settings['logger_serial'], asyncio.Lock())
    async with lock:
        return await hass.async_add_executor_job(read_sample, settings)

async def async_setup_entry(hass, entry):
    coordinator = MeterCoordinator(hass, entry)
    await coordinator.async_load_indexes()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
