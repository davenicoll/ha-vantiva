"""Builders for client model objects used by the integration tests.

Models are taken from `custom_components.vantiva.vantiva_client`, which is either the real
package or the stand-in installed by conftest.py.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

from custom_components.vantiva import vantiva_client as vc

try:
    ConnectionType = vc.ConnectionType
except AttributeError:  # real package may only export it from models
    ConnectionType = importlib.import_module(f"{vc.__name__}.models").ConnectionType

GATEWAY_MAC = "02:00:00:00:00:26"
FETCHED_AT = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
UPTIME = timedelta(days=49, hours=22, minutes=3, seconds=52)

CLIENT_ACTIVE_MAC = "02:00:00:00:00:02"
CLIENT_INACTIVE_MAC = "02:00:00:00:00:03"


def make_gateway(**overrides: Any) -> vc.GatewayInfo:
    values: dict[str, Any] = {
        "vendor": "Technicolor",
        "product": "NH20T",
        "serial": "CP0000000000",
        "software_version": "20.3.i.0565.17",
        "firmware_version": "20.3.i.0565-4629006-20260217054338.17",
        "hardware_version": "GCNT-K",
        "mac": GATEWAY_MAC,
        "uptime": UPTIME,
        "memory_pct": 54,
        "cpu_pct": 2,
        "reboot_cause": "User Initiated",
    }
    values.update(overrides)
    return vc.GatewayInfo(**values)


def make_wan(**overrides: Any) -> vc.WanStatus:
    values: dict[str, Any] = {
        "connected": True,
        "ipv4": "203.0.113.58",
        "ipv6": None,
        "gateway": "203.0.113.1",
        "dns": ("198.51.100.67", "198.51.100.116"),
        "lease_obtained": datetime(2026, 10, 1, 8, 0, 0),
        "lease_expires": datetime(2026, 10, 4, 8, 0, 0),
        "link_up": True,
        "gpon_up": True,
        "rx_bytes": 3939997125741,
        "tx_bytes": 1393232473707,
        "rx_packets": 1000,
        "tx_packets": 2000,
        "rx_errors": 0,
        "tx_errors": 0,
    }
    values.update(overrides)
    return vc.WanStatus(**values)


def make_gpon(**overrides: Any) -> vc.GponStats:
    values: dict[str, Any] = {
        "bandwidth_up_mbps": 10000,
        "bandwidth_down_mbps": 10000,
        "wavelength_up_nm": 1270,
        "wavelength_down_nm": 1577,
        "transceiver_type": "XGS-PON",
        "tx_power_dbm": 6.5236239,
        "rx_power_dbm": -17.544872,
        "bias_ma": 7.25,
        "vcc_v": 3.31,
        "temperature_c": 40.597656,
    }
    values.update(overrides)
    return vc.GponStats(**values)


def make_lan_client(mac: str, **overrides: Any) -> vc.LanClient:
    values: dict[str, Any] = {
        "mac": mac,
        "hostname": "device-01",
        "friendly_name": None,
        "ip": "192.168.1.117",
        "ipv6": None,
        "active": True,
        "connection": ConnectionType.WIRED,
        "interface": "eth4",
        "port": "5",
        "speed_mbps": 2500,
        "ssid": None,
        "lease_type": "DHCP",
        "vendor_class": "android-dhcp-14",
        "connected_since": datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC),
        "lease_remaining": timedelta(hours=12),
    }
    values.update(overrides)
    return vc.LanClient(**values)


def default_clients() -> dict[str, vc.LanClient]:
    return {
        CLIENT_ACTIVE_MAC: make_lan_client(CLIENT_ACTIVE_MAC),
        CLIENT_INACTIVE_MAC: make_lan_client(
            CLIENT_INACTIVE_MAC,
            hostname="device-02",
            ip="192.168.1.118",
            active=False,
            port="3",
            speed_mbps=1000,
            vendor_class=None,
            connected_since=None,
        ),
    }


_DEFAULT = object()


def make_data(
    *,
    gateway: vc.GatewayInfo | None = None,
    wan: vc.WanStatus | None = None,
    gpon: Any = _DEFAULT,
    clients: dict[str, vc.LanClient] | None = None,
    fetched_at: datetime = FETCHED_AT,
) -> vc.VantivaData:
    return vc.VantivaData(
        gateway=gateway or make_gateway(),
        wan=wan or make_wan(),
        gpon=make_gpon() if gpon is _DEFAULT else gpon,
        clients=default_clients() if clients is None else clients,
        fetched_at=fetched_at,
    )
