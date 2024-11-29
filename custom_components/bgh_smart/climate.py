"""BGH Smart integration."""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
#    PRESET_BOOST,
#    PRESET_COMFORT,
#    PRESET_ECO,
    PRESET_NONE,
#    PRESET_SLEEP,
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from aiohttp.client_exceptions import ClientError

from .const import DOMAIN, LOGGER, CONF_BACKEND, BACKEND_BGH, BACKEND_MYHABEETAT

PLATFORM_SCHEMA = CLIMATE_PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_BACKEND, default=BACKEND_BGH): vol.In(
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

#MAP_PRESET_MODE_ID = {
#    0: PRESET_NONE,
##    8: PRESET_BOOST,
#    16: PRESET_NONE,
#    24: PRESET_BOOST
#}

MAP_STATE_ICONS = {
    HVACMode.COOL: "mdi:snowflake",
    HVACMode.DRY: "mdi:water-off",
    HVACMode.FAN_ONLY: "mdi:fan",
    HVACMode.HEAT: "mdi:white-balance-sunny",
    HVACMode.HEAT_COOL: "mdi:cached",
}

SCAN_INTERVAL = timedelta(seconds=10)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BGH Smart entry."""
    from . import solidmation

    # Assign configuration variables.
    # The configuration check takes care they are present.
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    backend = entry.data.get(CONF_BACKEND) 

    # Setup connection with devices/cloud
    client = solidmation.SolidmationClient(username, password, backend, websession=async_get_clientsession(hass))
    try:
        await client.async_login()
    except (solidmation.AuthenticationException, solidmation.UnauthorizedException) as exception:
        LOGGER.error("Invalid credentials for BGH Smart cloud")
        raise ConfigEntryAuthFailed("Invalid credentials") from exception
    except (solidmation.LoginTimeoutException, ClientError, ConnectionError) as exception:
        raise ConfigEntryNotReady("Could not connect to {backend} with username {username}") from exception
    except Exception as ex:
        LOGGER.exception(ex)
        return False

    homes = await client.async_get_homes()

    # Verify that passed in configuration works
    if not homes:
        LOGGER.error("No homes defined on BGH Smart cloud")
        return

    # Add devices
    devices = []
    for home in homes:
        home_devices = await client.async_get_devices(home['HomeID'])
        for _device_id, device in home_devices.items():
            devices.append(device)

    entry.runtime_data = client

    async_add_entities(
        [ SolidmationHVAC(device, client) for device in devices ], True)


class SolidmationHVAC(ClimateEntity):
    """Representation of a BGH Smart HVAC."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1

    def __init__(self, device, client):
        """Initialize a BGH Smart HVAC."""
        self._device = device
        self._client = client

        self._device_name = self._device['device_name']
        self._device_id = self._device['device_id']
        self._home_id = self._device['device_data']['HomeID']
        self._attr_unique_id = "bgh_smart_{:x}".format(self._device['device_id'])
        self._attr_min_temp = None
        self._attr_max_temp = None
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = FAN_AUTO
        self._attr_swing_mode = SWING_OFF
        self._attr_preset_mode = PRESET_NONE
        self._attr_available = False

        self._parse_data()

        self._attr_hvac_modes = [HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT,
                            HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.OFF]
        self._attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._attr_swing_modes = [SWING_HORIZONTAL, SWING_OFF]
#        self._attr_preset_modes = [PRESET_NONE, PRESET_ECO, PRESET_BOOST, PRESET_SLEEP]

#        self._attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON)
        self._attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON)

    def _parse_data(self):
        """Parse the data in self._device"""
        # When the device is offline the API doesn't answer with the raw_data
        if self._device['raw_data']:
            self._attr_current_temperature = self._device['data']['temperature']
            self._attr_target_temperature = self._device['data']['target_temperature']
            self._attr_hvac_mode = MAP_MODE_ID[self._device['data']['mode_id']]
            self._attr_fan_mode = MAP_FAN_MODE_ID[self._device['data']['fan_speed']]
            self._attr_swing_mode = MAP_SWING_MODE_ID[self._device['data']['swing_mode']]
#            self._preset_mode = MAP_PRESET_MODE_ID[self._device['data']['preset_mode']]
        self._attr_available = self._device['data']['available']
        self._attr_min_temp = self._device['data']['min_temp']
        self._attr_max_temp = self._device['data']['max_temp']


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

    async def async_set_mode(self) -> None:
        """Push the settings to the unit."""
        await self._client.async_set_mode(
            self._device_id,
            self._attr_hvac_mode,
            self._attr_target_temperature,
            self._attr_fan_mode,
            self._attr_swing_mode,
            self._attr_preset_mode)
        await self.async_update()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        operation_mode = kwargs.get(ATTR_HVAC_MODE)

        if temperature:
            self._attr_target_temperature = temperature

        if operation_mode:
            self._attr_hvac_mode = operation_mode

        await self.async_set_mode()

    async def async_set_hvac_mode(self, operation_mode) -> None:
        """Set new target operation mode."""
        self._attr_hvac_mode = operation_mode
        await self.async_set_mode()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        self._attr_fan_mode = fan_mode
        await self.async_set_mode()

    async def async_set_swing_mode(self, swing_mode) -> None:
        self._attr_swing_mode = swing_mode
        await self.async_set_mode()

#    async def async_set_preset_mode(self, preset_mode) -> None:
#        self._attr_preset_mode = preset_mode
#        await self.async_set_mode()

    @property
    def icon(self):
        """Return the icon for the current state."""
        icon = None
        if self._attr_hvac_mode != HVACMode.OFF:
            icon = MAP_STATE_ICONS.get(self._attr_hvac_mode)
        return icon