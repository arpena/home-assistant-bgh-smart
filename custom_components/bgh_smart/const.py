"""Constants for the Sagemcom F@st integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

LOGGER: logging.Logger = logging.getLogger(__package__)

DOMAIN: Final = "bgh_smart"
INTEGRATION_NAME: Final = "BGH Smart Cloud"

ATTR_MANUFACTURER: Final = "BGH"

MIN_SCAN_INTERVAL: Final = 10
DEFAULT_SCAN_INTERVAL: Final = 10

PLATFORMS: list[Platform] = [Platform.CLIMATE]

BACKEND_BGH: Final = "bgh"
BACKEND_MYHABEETAT: Final = "myhabeetat"
CONF_BACKEND: Final = "backend"