"""Binary sensors for the Vantiva integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VantivaData
from .coordinator import VantivaConfigEntry
from .entity import VantivaEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VantivaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Vantiva binary sensor."""

    value_fn: Callable[[VantivaData], bool | None]


BINARY_SENSORS: tuple[VantivaBinarySensorEntityDescription, ...] = (
    VantivaBinarySensorEntityDescription(
        key="internet_connected",
        translation_key="internet_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.wan.connected,
    ),
    VantivaBinarySensorEntityDescription(
        key="wan_link",
        translation_key="wan_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.wan.link_up,
    ),
    VantivaBinarySensorEntityDescription(
        key="gpon_link",
        translation_key="gpon_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.wan.gpon_up,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VantivaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vantiva binary sensors whose data the gateway provides."""
    coordinator = entry.runtime_data
    async_add_entities(
        VantivaBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.value_fn(coordinator.data) is not None
    )


class VantivaBinarySensor(VantivaEntity, BinarySensorEntity):
    """A gateway binary sensor."""

    entity_description: VantivaBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.coordinator.data)
