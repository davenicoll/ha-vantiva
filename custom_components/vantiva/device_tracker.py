"""Device trackers for LAN clients seen by the Vantiva gateway."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import LanClient
from .coordinator import VantivaConfigEntry, VantivaCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VantivaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a tracker per LAN client and add new clients as they appear."""
    coordinator = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def _async_add_new_clients() -> None:
        new_macs = [mac for mac in coordinator.data.clients if mac not in tracked]
        if not new_macs:
            return
        tracked.update(new_macs)
        async_add_entities(VantivaDeviceTracker(coordinator, mac) for mac in new_macs)

    _async_add_new_clients()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_clients))


class VantivaDeviceTracker(CoordinatorEntity[VantivaCoordinator], ScannerEntity):
    """Presence of one LAN client.

    Trackers deliberately have no device_info: ScannerEntity links them to a device registry
    entry by MAC connection, so they are not attached to the gateway device.
    """

    _attr_has_entity_name = True
    _attr_source_type = SourceType.ROUTER

    def __init__(self, coordinator: VantivaCoordinator, mac: str) -> None:
        """Initialise the tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_mac_address = mac
        self._client: LanClient | None = None
        self._update_from_data()

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Enable trackers by default; this integration's main purpose is presence."""
        return True

    @property
    def is_connected(self) -> bool:
        """Return True if the client is (or recently was) connected."""
        return self.coordinator.is_client_home(self._mac)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details reported by the gateway."""
        client = self._client
        if client is None:
            return {}
        connection = client.connection
        return {
            "connection": getattr(connection, "value", connection),
            "interface": client.interface,
            "port": client.port,
            "speed_mbps": client.speed_mbps,
            "ssid": client.ssid,
            "vendor_class": client.vendor_class,
        }

    def _update_from_data(self) -> None:
        client = self.coordinator.data.clients.get(self._mac)
        if client is not None:
            self._client = client
            self._attr_ip_address = client.ip
            self._attr_hostname = client.hostname
            self._attr_name = client.friendly_name or client.hostname or self._mac

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()
