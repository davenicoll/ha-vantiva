"""Sensors for the Vantiva integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import GponStats
from .coordinator import VantivaConfigEntry, VantivaCoordinator
from .entity import VantivaEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VantivaSensorEntityDescription(SensorEntityDescription):
    """Describes a Vantiva sensor."""

    value_fn: Callable[[VantivaCoordinator], StateType | datetime]


def _gpon(attr: str) -> Callable[[VantivaCoordinator], StateType]:
    def _value(coordinator: VantivaCoordinator) -> StateType:
        gpon: GponStats | None = coordinator.data.gpon
        return getattr(gpon, attr) if gpon is not None else None

    return _value


SENSORS: tuple[VantivaSensorEntityDescription, ...] = (
    VantivaSensorEntityDescription(
        key="wan_ipv4",
        translation_key="wan_ipv4",
        value_fn=lambda c: c.data.wan.ipv4,
    ),
    VantivaSensorEntityDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_boot,
    ),
    VantivaSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.gateway.firmware_version,
    ),
    VantivaSensorEntityDescription(
        key="hardware_version",
        translation_key="hardware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.gateway.hardware_version,
    ),
    VantivaSensorEntityDescription(
        key="connected_clients",
        translation_key="connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.active_client_count,
    ),
    VantivaSensorEntityDescription(
        key="total_clients",
        translation_key="total_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: len(c.data.clients),
    ),
    VantivaSensorEntityDescription(
        key="cpu_pct",
        translation_key="cpu_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.gateway.cpu_pct,
    ),
    VantivaSensorEntityDescription(
        key="memory_pct",
        translation_key="memory_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.gateway.memory_pct,
    ),
    VantivaSensorEntityDescription(
        key="wan_rx_bytes",
        translation_key="wan_rx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.data.wan.rx_bytes,
    ),
    VantivaSensorEntityDescription(
        key="wan_tx_bytes",
        translation_key="wan_tx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.data.wan.tx_bytes,
    ),
    VantivaSensorEntityDescription(
        key="dns_servers",
        translation_key="dns_servers",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: ", ".join(c.data.wan.dns) or None,
    ),
    VantivaSensorEntityDescription(
        key="wan_gateway",
        translation_key="wan_gateway",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.wan.gateway,
    ),
)

GPON_SENSORS: tuple[VantivaSensorEntityDescription, ...] = (
    VantivaSensorEntityDescription(
        key="gpon_rx_power_dbm",
        translation_key="gpon_rx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_gpon("rx_power_dbm"),
    ),
    VantivaSensorEntityDescription(
        key="gpon_tx_power_dbm",
        translation_key="gpon_tx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_gpon("tx_power_dbm"),
    ),
    VantivaSensorEntityDescription(
        key="gpon_temperature_c",
        translation_key="gpon_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_gpon("temperature_c"),
    ),
    VantivaSensorEntityDescription(
        key="gpon_bias_ma",
        translation_key="gpon_bias",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_gpon("bias_ma"),
    ),
    VantivaSensorEntityDescription(
        key="gpon_vcc_v",
        translation_key="gpon_vcc",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_gpon("vcc_v"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VantivaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vantiva sensors."""
    coordinator = entry.runtime_data
    descriptions = list(SENSORS)
    if coordinator.data.gpon is not None:
        descriptions.extend(GPON_SENSORS)
    async_add_entities(VantivaSensor(coordinator, description) for description in descriptions)


class VantivaSensor(VantivaEntity, SensorEntity):
    """A gateway sensor."""

    entity_description: VantivaSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator)
