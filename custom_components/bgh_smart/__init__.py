"""BGH Smart integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up BGH Smart from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok

#async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
#    """Update when entry options update."""
#    if entry.options[CONF_SCAN_INTERVAL]:
#        data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
#        data.coordinator.update_interval = timedelta(
#            seconds=entry.options[CONF_SCAN_INTERVAL]
#        )
#
#        await data.coordinator.async_refresh()