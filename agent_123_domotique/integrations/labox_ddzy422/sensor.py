from datetime import datetime, timezone
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STALE_SECONDS

DESCRIPTIONS = (
    SensorEntityDescription(key='gridPowerW',name='Puissance réseau',device_class=SensorDeviceClass.POWER,native_unit_of_measurement='W',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='importPowerW',name='Soutirage',device_class=SensorDeviceClass.POWER,native_unit_of_measurement='W',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='exportPowerW',name='Injection',device_class=SensorDeviceClass.POWER,native_unit_of_measurement='W',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='importTotalKwh',name='Index soutirage',device_class=SensorDeviceClass.ENERGY,native_unit_of_measurement='kWh',state_class=SensorStateClass.TOTAL_INCREASING),
    SensorEntityDescription(key='exportTotalKwh',name='Index injection',device_class=SensorDeviceClass.ENERGY,native_unit_of_measurement='kWh',state_class=SensorStateClass.TOTAL_INCREASING),
    SensorEntityDescription(key='voltageV',name='Tension',device_class=SensorDeviceClass.VOLTAGE,native_unit_of_measurement='V',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='currentA',name='Courant',device_class=SensorDeviceClass.CURRENT,native_unit_of_measurement='A',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='frequencyHz',name='Fréquence',device_class=SensorDeviceClass.FREQUENCY,native_unit_of_measurement='Hz',state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key='powerFactor',name='Facteur de puissance',state_class=SensorStateClass.MEASUREMENT),
)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(MeterSensor(entry.runtime_data, desc) for desc in DESCRIPTIONS)

class MeterSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.settings['logger_serial']
        self._attr_unique_id = f'{DOMAIN}_{serial}_{description.key}'
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN,str(serial))},name=f'Compteur DDZY422 {serial}',manufacturer='Solarman',model='DDZY422-D2')

    @property
    def available(self):
        if not super().available or not self.coordinator.data:return False
        try:
            at=datetime.fromisoformat(self.coordinator.data['readAtUtc'])
            return 0 <= (datetime.now(timezone.utc)-at).total_seconds() < STALE_SECONDS
        except (KeyError,ValueError,TypeError):return False

    @property
    def native_value(self):
        if not self.available:return None
        values=self.coordinator.data['values'];key=self.entity_description.key
        if key=='importPowerW':return max(0,values['gridPowerW'])
        if key=='exportPowerW':return max(0,-values['gridPowerW'])
        return values.get(key)

    @property
    def extra_state_attributes(self):
        return {'measurement_time':self.coordinator.data.get('readAtUtc') if self.coordinator.data else None,
                'source':'local_identity_crc_verified','grid_sign_convention':'positive_import_negative_export'}
