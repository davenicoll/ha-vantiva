"""Constants for the Vantiva integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "vantiva"
LOGGER = logging.getLogger(__package__)

DEFAULT_USERNAME: Final = "admin"

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_CONSIDER_HOME: Final = "consider_home"

DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600

DEFAULT_CONSIDER_HOME: Final = 180
MIN_CONSIDER_HOME: Final = 0
MAX_CONSIDER_HOME: Final = 3600

# Changes in the computed boot time smaller than this are treated as polling jitter.
LAST_BOOT_TOLERANCE_SECONDS: Final = 60

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]
