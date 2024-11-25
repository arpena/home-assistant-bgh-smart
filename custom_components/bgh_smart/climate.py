"""BGH Smart integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    PRESET_SLEEP,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_VERTICAL,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_PASSWORD,
    CONF_USERNAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

BACKEND_BGH = "bgh"
BACKEND_MYHABEETAT = "myhabeetat"

PLATFORM_SCHEMA = CLIMATE_PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional("backend", default=BACKEND_BGH): vol.In(
        [BACKEND_BGH, BACKEND_MYHABEETAT]
    )
})

MAP_MODE_ID = {
    0: HVACMode.OFF,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    254: HVACMode.AUTO
}

MAP_FAN_MODE_ID = {
    1: FAN_LOW,
    2: FAN_MEDIUM,
    3: FAN_HIGH,
    254: FAN_AUTO
}

MAP_SWING_MODE_ID = {
    0: SWING_OFF,
    8: SWING_OFF,
    16: SWING_HORIZONTAL,
    24: SWING_HORIZONTAL
}

MAP_PRESET_MODE_ID = {
    0: PRESET_NONE,
    8: PRESET_BOOST,
    16: PRESET_NONE,
    24: PRESET_BOOST
}


SCAN_INTERVAL = timedelta(seconds=10)

async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType, 
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None
        ) -> None:
    """Set up the BGH Smart platform."""
    from . import solidmation

    # Assign configuration variables.
    # The configuration check takes care they are present.
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    backend = config.get("backend") 

    # Setup connection with devices/cloud
    client = solidmation.SolidmationClient(username, password, backend, websession=async_get_clientsession(hass))

    homes = await client.async_get_homes()

    # Verify that passed in configuration works
    if not homes:
        _LOGGER.error("Could not connect to BGH Smart cloud")
        return

    # Add devices
    devices = []
    for home in homes:
        home_devices = await client.async_get_devices(home['HomeID'])
        for _device_id, device in home_devices.items():
            devices.append(device)

    async_add_entities(
        [ SolidmationHVAC(device, client) for device in devices ], True)


class SolidmationHVAC(ClimateEntity):
    """Representation of a BGH Smart HVAC."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, device, client):
        """Initialize a BGH Smart HVAC."""
        self._device = device
        self._client = client

        self._device_name = self._device['device_name']
        self._device_id = self._device['device_id']
        # add a unique device id
        self._device_unique_id = self._device['device_id']
        #self._attr_unique_id = self._device['device_id']
        # not sure which one is the right one
        self._home_id = self._device['device_data']['HomeID']
        self._min_temp = None
        self._max_temp = None
        self._current_temperature = None
        self._target_temperature = None
        self._mode = HVACMode.OFF
        self._fan_speed = FAN_AUTO
        self._swing_mode = SWING_OFF
        self._preset_mode = PRESET_NONE

        self._parse_data()

        self._hvac_modes = [HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT,
                            HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.OFF]
        self._fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._swing_modes = [SWING_HORIZONTAL, SWING_OFF]
        self._preset_modes = [PRESET_NONE, PRESET_ECO, PRESET_BOOST, PRESET_SLEEP]

        self._support = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE | ClimateEntityFeature.PRESET_MODE)

    def _parse_data(self):
        """Parse the data in self._device"""
        self._min_temp = 17
        self._max_temp = 30

        # Sometimes the API doesn't answer with the raw_data
        if self._device['raw_data']:
            self._current_temperature = self._device['data']['temperature']
            self._target_temperature = self._device['data']['target_temperature']
            self._mode = MAP_MODE_ID[self._device['data']['mode_id']]
            self._fan_speed = MAP_FAN_MODE_ID[self._device['data']['fan_speed']]
            self._swing_mode = MAP_SWING_MODE_ID[self._device['data']['swing_mode']]
            self._preset_mode = MAP_PRESET_MODE_ID[self._device['data']['swing_mode']]

    async def async_update(self) -> None:
        """Fetch new state data for this HVAC.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._device = await self._client.async_get_status(self._home_id, self._device_id)
        self._parse_data()

    @property
    def name(self):
        """Return the display name of this HVAC."""
        return self._device_name

    @property
    def unique_id(self):
        return self._device_id

    @property
    def temperature_unit(self):
        """BGH Smart API uses celsius on the backend."""
        return self._attr_temperature_unit

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature for the current mode of operation."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature for the current mode of operation."""
        return self._max_temp

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support

    @property
    def hvac_mode(self):
        """Return the current mode of operation if unit is on."""
        return self._mode

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_modes

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        return self._fan_speed

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return self._fan_modes

    @property
    def preset_modes(self):
        return self._preset_modes

    async def async_set_mode(self) -> None:
        """Push the settings to the unit."""
        await self._client.async_set_mode(
            self._device_id,
            self._mode,
            self._target_temperature,
            self._fan_speed,
            self._swing_mode,
            self._preset_mode)

        await self.async_update()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        operation_mode = kwargs.get(ATTR_HVAC_MODE)

        if temperature:
            self._target_temperature = temperature

        if operation_mode:
            self._mode = operation_mode

        await self.async_set_mode()

    async def async_set_hvac_mode(self, operation_mode) -> None:
        """Set new target operation mode."""
        self._mode = operation_mode
        await self.async_set_mode()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        self._fan_speed = fan_mode
        await self.async_set_mode()

    # SWING
    @property
    def swing_mode(self):
        """Return the list of available swing modes."""
        return self._swing_mode

    @property
    def swing_modes(self):
        """Return the list of available swing modes."""
        return self._swing_modes

    async def async_set_swing_mode(self, swing_mode) -> None:
        self._swing_mode = swing_mode
        await self.async_set_mode()

    # PRESET
    @property
    def preset_mode(self):
        return self._preset_mode

    async def async_set_preset_mode(self, preset_mode) -> None:
        self._preset_mode = preset_mode
        await self.async_set_mode()
