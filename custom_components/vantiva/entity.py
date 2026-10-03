"""Base entity for the Vantiva integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VantivaCoordinator


def gateway_id(coordinator: VantivaCoordinator) -> str:
    """Return the stable identifier of the gateway (its MAC, set as the entry unique ID)."""
    return coordinator.config_entry.unique_id or coordinator.config_entry.entry_id


class VantivaEntity(CoordinatorEntity[VantivaCoordinator]):
    """An entity that belongs to the gateway device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VantivaCoordinator, description: EntityDescription) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        uid = gateway_id(coordinator)
        self._attr_unique_id = f"{uid}_{description.key}"
        gateway = coordinator.data.gateway
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            connections={(CONNECTION_NETWORK_MAC, gateway.mac)} if gateway.mac else set(),
            manufacturer="Vantiva",
            model=gateway.product,
            name=gateway.product or "Vantiva gateway",
            sw_version=gateway.software_version,
            hw_version=gateway.hardware_version,
            serial_number=gateway.serial,
            configuration_url=coordinator.client.base_url,
        )
