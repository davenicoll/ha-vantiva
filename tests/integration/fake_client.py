"""Stand-in for `custom_components.vantiva.vantiva_client` matching docs/CLIENT_API.md.

Only used when the real vendored client package is absent (the integration and the client are
developed on separate branches). conftest.py installs this module under the real package name in
`sys.modules` before Home Assistant imports the integration. Once the real package is present,
it is used instead and this module is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class VantivaError(Exception):
    """Base error."""


class VantivaConnectionError(VantivaError):
    """Transport error."""


class VantivaAuthError(VantivaError):
    """Credentials rejected."""


class VantivaLockedOutError(VantivaAuthError):
    """Account locked after failed logins."""

    def __init__(
        self,
        msg: str = "locked out",
        wait_seconds: int | None = None,
        wrong_count: int | None = None,
    ) -> None:
        super().__init__(msg)
        self.wait_seconds = wait_seconds
        self.wrong_count = wrong_count


class VantivaParseError(VantivaError):
    """Unexpected page structure."""


class ConnectionType(StrEnum):
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
    mac: str
    hostname: str | None
    friendly_name: str | None
    ip: str | None
    ipv6: str | None
    active: bool
    connection: ConnectionType
    interface: str | None
    port: str | None
    speed_mbps: int | None
    ssid: str | None
    lease_type: str | None
    vendor_class: str | None
    connected_since: datetime | None
    lease_remaining: timedelta | None


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    vendor: str | None
    product: str | None
    serial: str | None
    software_version: str | None
    firmware_version: str | None
    hardware_version: str | None
    mac: str | None
    uptime: timedelta | None
    memory_pct: int | None
    cpu_pct: int | None
    reboot_cause: str | None


@dataclass(frozen=True, slots=True)
class WanStatus:
    connected: bool
    ipv4: str | None
    ipv6: str | None
    gateway: str | None
    dns: tuple[str, ...]
    lease_obtained: datetime | None
    lease_expires: datetime | None
    link_up: bool | None
    gpon_up: bool | None
    rx_bytes: int | None
    tx_bytes: int | None
    rx_packets: int | None
    tx_packets: int | None
    rx_errors: int | None
    tx_errors: int | None


@dataclass(frozen=True, slots=True)
class GponStats:
    bandwidth_up_mbps: int | None
    bandwidth_down_mbps: int | None
    wavelength_up_nm: int | None
    wavelength_down_nm: int | None
    transceiver_type: str | None
    tx_power_dbm: float | None
    rx_power_dbm: float | None
    bias_ma: float | None
    vcc_v: float | None
    temperature_c: float | None


@dataclass(frozen=True, slots=True)
class VantivaData:
    gateway: GatewayInfo
    wan: WanStatus
    gpon: GponStats | None
    clients: dict[str, LanClient]
    fetched_at: datetime

    @property
    def active_client_count(self) -> int:
        return sum(1 for c in self.clients.values() if c.active)


class VantivaClient:
    """Signature-only stand-in; tests always replace it with a mock."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: Any,
        *,
        request_timeout: float = 15.0,
        verify_ssl: bool = True,
    ) -> None:
        raise RuntimeError("fake VantivaClient must be patched in tests")


__all__ = [
    "ConnectionType",
    "GatewayInfo",
    "GponStats",
    "LanClient",
    "VantivaAuthError",
    "VantivaClient",
    "VantivaConnectionError",
    "VantivaData",
    "VantivaError",
    "VantivaLockedOutError",
    "VantivaParseError",
    "WanStatus",
]
