try:
    import probatio as vol
except ImportError:  # HA versions before the core schema-library migration.
    import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST
from .const import DOMAIN
from .transport import validate_settings, validate_local_host
from . import async_read

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                settings = validate_settings(user_input[CONF_HOST], user_input['logger_serial'], user_input['mac'])
                validate_local_host(settings[CONF_HOST], await network.async_get_adapters(self.hass))
                await self.async_set_unique_id(str(settings['logger_serial']))
                existing = next((e for e in self._async_current_entries() if e.unique_id == self.unique_id), None)
                if existing:
                    if existing.data.get('mac') != settings['mac']:
                        return self.async_abort(reason='identity_mismatch')
                    if existing.data.get(CONF_HOST) == settings[CONF_HOST]:
                        return self.async_abort(reason='already_configured')
                await async_read(self.hass, settings)
                self._abort_if_unique_id_configured(updates={CONF_HOST: settings[CONF_HOST]})
            except (ValueError, KeyError, TypeError):
                errors['base'] = 'invalid_settings'
            except (OSError, TimeoutError):
                errors['base'] = 'cannot_connect'
            else:
                return self.async_create_entry(title=f"Compteur DDZY422 {settings['logger_serial']}", data=settings)
        return self.async_show_form(step_id='user', data_schema=vol.Schema({
            vol.Required(CONF_HOST):str, vol.Required('logger_serial'):int, vol.Required('mac'):str}), errors=errors)
