from datetime import datetime, timedelta, timezone
import logging
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.network.network import async_get_network
from homeassistant.components.network.util import (
    async_load_adapters, enable_adapters, enable_auto_detected_adapters,
)
from .const import DOMAIN, POLL_SECONDS
from .transport import IndexGuard, validate_local_host

_LOGGER = logging.getLogger(__name__)

async def current_adapters(hass):
    """Re-enumerate after DHCP changes without mutating global network settings.

    Core's adapter cache may have been loaded before Ethernet acquired an IP.
    Keep its configured-interface policy, but never validate against stale IPs.
    Enumeration failure propagates before any meter read or index checkpoint.
    """
    configured = (await async_get_network(hass)).configured_adapters
    adapters = await async_load_adapters()
    if not enable_adapters(adapters, configured):
        enable_auto_detected_adapters(adapters)
    return adapters


class MeterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=POLL_SECONDS))
        self.settings = dict(entry.data)
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.data['logger_serial']}.indexes", private=True)
        self.guard = IndexGuard()

    async def async_load_indexes(self):
        self.guard = IndexGuard(await self.store.async_load())

    async def _async_update_data(self):
        from . import async_read
        try:
            adapters = await current_adapters(self.hass)
            validate_local_host(self.settings['host'], adapters)
            sample = await async_read(self.hass, self.settings)
            at = datetime.fromisoformat(sample['readAtUtc']).timestamp()
            previous = self.guard.previous
            checkpoint = self.guard.validate(sample['values'], at)
            try:
                await self.store.async_save(checkpoint)
            except Exception:
                self.guard.previous = previous
                raise
            return sample
        except Exception as error:
            # No device addresses, raw frames, credentials or guessed zeroes.
            raise UpdateFailed('Lecture locale du compteur non vérifiée ; les mesures restent indisponibles.') from error
