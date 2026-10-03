"""Data models returned by the Vantiva client library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ConnectionType(StrEnum):
    """How a LAN client is attached to the gateway."""

    WIRED = "wired"
    WIFI_2G = "wifi_2g"
    WIFI_5G = "wifi_5g"
    WIFI_6G = "wifi_6g"
    WIFI_GUEST_2G = "wifi_guest_2g"
    WIFI_GUEST_5G = "wifi_guest_5g"
    MOCA = "moca"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LanClient:
    """A device known to the gateway's LAN host table."""

    mac: str
    hostname: str | None = None
    friendly_name: str | None = None
    ip: str | None = None
    ipv6: str | None = None
    active: bool = False
    connection: ConnectionType = ConnectionType.UNKNOWN
    interface: str | None = None
    port: str | None = None
    speed_mbps: int | None = None
    ssid: str | None = None
    lease_type: str | None = None
    vendor_class: str | None = None
    connected_since: datetime | None = None
    lease_remaining: timedelta | None = None


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """Gateway identity and health from the system information page."""

    vendor: str | None = None
    product: str | None = None
    serial: str | None = None
    software_version: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    mac: str | None = None
    uptime: timedelta | None = None
    memory_pct: int | None = None
    cpu_pct: int | None = None
    reboot_cause: str | None = None


@dataclass(frozen=True, slots=True)
class WanStatus:
    """WAN (internet) connection state and counters."""

    connected: bool = False
    ipv4: str | None = None
    ipv6: str | None = None
    gateway: str | None = None
    dns: tuple[str, ...] = ()
    lease_obtained: datetime | None = None
    lease_expires: datetime | None = None
    link_up: bool | None = None
    gpon_up: bool | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    rx_packets: int | None = None
    tx_packets: int | None = None
    rx_errors: int | None = None
    tx_errors: int | None = None


@dataclass(frozen=True, slots=True)
class GponStats:
    """GPON optical module statistics."""

    bandwidth_up_mbps: int | None = None
    bandwidth_down_mbps: int | None = None
    wavelength_up_nm: int | None = None
    wavelength_down_nm: int | None = None
    transceiver_type: str | None = None
    tx_power_dbm: float | None = None
    rx_power_dbm: float | None = None
    bias_ma: float | None = None
    vcc_v: float | None = None
    temperature_c: float | None = None


@dataclass(frozen=True, slots=True)
class VantivaData:
    """A complete snapshot of the gateway state."""

    gateway: GatewayInfo
    wan: WanStatus
    gpon: GponStats | None
    clients: dict[str, LanClient]
    fetched_at: datetime

    @property
    def active_client_count(self) -> int:
        """Return the number of clients currently marked active."""
        return sum(1 for client in self.clients.values() if client.active)
