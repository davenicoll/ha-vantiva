"""Data update coordinator for the Vantiva integration."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    VantivaAuthError,
    VantivaClient,
    VantivaData,
    VantivaError,
    VantivaLockedOutError,
)
from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LAST_BOOT_TOLERANCE_SECONDS,
    LOGGER,
)

type VantivaConfigEntry = ConfigEntry[VantivaCoordinator]


class VantivaCoordinator(DataUpdateCoordinator[VantivaData]):
    """Poll the gateway and hold the latest snapshot."""

    config_entry: VantivaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: VantivaConfigEntry,
        client: VantivaClient,
    ) -> None:
        """Initialise the coordinator."""
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.consider_home = timedelta(
            seconds=config_entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        )
        # Last time the router reported each MAC as active (used for consider_home).
        self.last_seen: dict[str, datetime] = {}
        # Boot time derived from uptime, held stable against polling jitter.
        self.last_boot: datetime | None = None

    async def _async_update_data(self) -> VantivaData:
        """Fetch a fresh snapshot from the gateway."""
        try:
            data = await self.client.async_get_data()
        except VantivaLockedOutError as err:
            # The account is temporarily locked (often by failed GUI logins). The stored
            # password may still be correct, so retry later instead of asking for reauth.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="locked_out",
                translation_placeholders={"wait": str(err.wait_seconds or "unknown")},
            ) from err
        except VantivaAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except VantivaError as err:
            # VantivaConnectionError, VantivaParseError and anything else from the client.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err

        now = dt_util.utcnow()
        for mac, client in data.clients.items():
            if client.active:
                self.last_seen[mac] = now
        self._update_last_boot(data)
        return data

    def _update_last_boot(self, data: VantivaData) -> None:
        """Recompute the boot time, ignoring changes below the tolerance."""
        uptime = data.gateway.uptime
        if uptime is None:
            return
        boot = (data.fetched_at - uptime).replace(microsecond=0)
        if (
            self.last_boot is None
            or abs((boot - self.last_boot).total_seconds()) >= LAST_BOOT_TOLERANCE_SECONDS
        ):
            self.last_boot = boot

    def is_client_home(self, mac: str) -> bool:
        """Return True if the client is active or was active within consider_home."""
        if (client := self.data.clients.get(mac)) is not None and client.active:
            return True
        last_seen = self.last_seen.get(mac)
        return last_seen is not None and dt_util.utcnow() - last_seen < self.consider_home
