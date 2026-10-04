"""Sensor, binary sensor and device tracker tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from custom_components.vantiva.const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .factories import (
    CLIENT_ACTIVE_MAC,
    CLIENT_INACTIVE_MAC,
    FETCHED_AT,
    GATEWAY_MAC,
    UPTIME,
    default_clients,
    make_data,
    make_gateway,
    make_lan_client,
    make_wan,
)


async def _poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int = DEFAULT_SCAN_INTERVAL + 1
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_gateway_device(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, GATEWAY_MAC), init_integration.entry_id
    )
    assert device is not None
    assert device.manufacturer == "Vantiva"
    assert device.model == "NH20T"
    assert device.sw_version == "20.3.i.0565.17"
    assert device.hw_version == "GCNT-K"
    assert device.serial_number == "CP0000000000"
    assert device.configuration_url == "http://192.168.1.254"


async def test_sensors(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    assert hass.states.get("sensor.nh20t_wan_ipv4_address").state == "203.0.113.58"
    assert hass.states.get("sensor.nh20t_connected_clients").state == "1"
    known = hass.states.get("sensor.nh20t_known_clients")
    assert known.state == "2"
    assert len(known.attributes["clients"]) == 2
    connected = hass.states.get("sensor.nh20t_connected_clients")
    assert [c["mac"] for c in connected.attributes["clients"]] == [CLIENT_ACTIVE_MAC]
    client = connected.attributes["clients"][0]
    assert client["hostname"] == "device-01"
    assert client["ip"] == "192.168.1.117"
    assert client["active"] is True
    assert client["connection"] == "wired"
    assert client["port"] == "5"
    assert client["speed_mbps"] == 2500
    assert hass.states.get("sensor.nh20t_cpu_usage").state == "2"
    assert hass.states.get("sensor.nh20t_dns_servers").state == "198.51.100.67, 198.51.100.116"
    assert float(hass.states.get("sensor.nh20t_gpon_receive_power").state) == -17.544872

    rx = hass.states.get("sensor.nh20t_wan_received")
    assert rx.attributes["unit_of_measurement"] == "GB"
    assert rx.attributes["state_class"] == "total_increasing"
    assert float(rx.state) == pytest.approx(3939.997, abs=0.01)

    boot = hass.states.get("sensor.nh20t_last_boot")
    assert boot.state == (FETCHED_AT - UPTIME).isoformat()

    entry = er.async_get(hass).async_get("sensor.nh20t_wan_ipv4_address")
    assert entry.unique_id == f"{GATEWAY_MAC}_wan_ipv4"


async def test_last_boot_ignores_jitter(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    entity_id = "sensor.nh20t_last_boot"
    original = hass.states.get(entity_id).state

    # Fetched 30 s later but uptime only advanced 1 s: boot time moves by 29 s -> ignored.
    mock_client.async_get_data.return_value = make_data(
        fetched_at=FETCHED_AT + timedelta(seconds=30),
        gateway=make_gateway(uptime=UPTIME + timedelta(seconds=1)),
    )
    await _poll(hass, freezer)
    assert hass.states.get(entity_id).state == original

    # A reboot: uptime drops to 5 minutes.
    mock_client.async_get_data.return_value = make_data(
        fetched_at=FETCHED_AT + timedelta(hours=1),
        gateway=make_gateway(uptime=timedelta(minutes=5)),
    )
    await _poll(hass, freezer)
    expected = FETCHED_AT + timedelta(hours=1) - timedelta(minutes=5)
    assert hass.states.get(entity_id).state == expected.isoformat()


async def test_no_gpon_sensors_without_gpon(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.async_get_data.return_value = make_data(
        gpon=None, wan=make_wan(gpon_up=None, link_up=None)
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.nh20t_gpon_receive_power") is None
    assert hass.states.get("binary_sensor.nh20t_gpon_link") is None
    assert hass.states.get("binary_sensor.nh20t_wan_link") is None
    assert hass.states.get("binary_sensor.nh20t_internet") is not None


async def test_binary_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    state = hass.states.get("binary_sensor.nh20t_internet")
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "connectivity"
    assert hass.states.get("binary_sensor.nh20t_gpon_link").state == STATE_ON
    assert hass.states.get("binary_sensor.nh20t_wan_link").state == STATE_ON

    mock_client.async_get_data.return_value = make_data(wan=make_wan(connected=False))
    await _poll(hass, freezer)
    assert hass.states.get("binary_sensor.nh20t_internet").state == STATE_OFF


async def test_device_trackers(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    active = hass.states.get("device_tracker.device_01")
    assert active.state == STATE_HOME
    assert active.attributes["ip"] == "192.168.1.117"
    assert active.attributes["mac"] == CLIENT_ACTIVE_MAC
    assert active.attributes["host_name"] == "device-01"
    assert active.attributes["source_type"] == "router"
    assert active.attributes["connection"] == "wired"
    assert active.attributes["port"] == "5"
    assert active.attributes["speed_mbps"] == 2500
    assert active.attributes["interface"] == "eth4"
    assert active.attributes["vendor_class"] == "android-dhcp-14"

    inactive = hass.states.get("device_tracker.device_02")
    assert inactive.state == STATE_NOT_HOME

    reg_entry = er.async_get(hass).async_get("device_tracker.device_01")
    assert reg_entry.unique_id == CLIENT_ACTIVE_MAC
    # Trackers are not attached to the gateway device.
    gateway = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, GATEWAY_MAC), init_integration.entry_id
    )
    assert reg_entry.device_id != gateway.id


async def test_tracker_consider_home(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    entity_id = "device_tracker.device_01"
    clients = default_clients()
    clients[CLIENT_ACTIVE_MAC] = make_lan_client(CLIENT_ACTIVE_MAC, active=False)
    mock_client.async_get_data.return_value = make_data(clients=clients)

    # Default consider_home (180 s) is shorter than the default poll interval (300 s), so a
    # client that has gone inactive is reported away at the very next poll.
    await _poll(hass, freezer)
    assert hass.states.get(entity_id).state == STATE_NOT_HOME

    # With a longer consider_home window the client stays home until the window has passed.
    clients[CLIENT_ACTIVE_MAC] = make_lan_client(CLIENT_ACTIVE_MAC, active=True)
    mock_client.async_get_data.return_value = make_data(clients=clients)
    hass.config_entries.async_update_entry(
        init_integration,
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_CONSIDER_HOME: 1000},
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_HOME

    clients[CLIENT_ACTIVE_MAC] = make_lan_client(CLIENT_ACTIVE_MAC, active=False)
    mock_client.async_get_data.return_value = make_data(clients=clients)
    await _poll(hass, freezer)  # ~301 s without being seen: still within 1000 s
    assert hass.states.get(entity_id).state == STATE_HOME
    for _ in range(3):
        await _poll(hass, freezer)  # ~1204 s: past the window
    assert hass.states.get(entity_id).state == STATE_NOT_HOME


async def test_new_tracker_added_dynamically(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    new_mac = "02:00:00:00:00:04"
    assert hass.states.get("device_tracker.laptop") is None

    clients = default_clients()
    clients[new_mac] = make_lan_client(new_mac, hostname="laptop", ip="192.168.1.120")
    mock_client.async_get_data.return_value = make_data(clients=clients)
    await _poll(hass, freezer)

    state = hass.states.get("device_tracker.laptop")
    assert state is not None
    assert state.state == STATE_HOME
    assert hass.states.get("sensor.nh20t_known_clients").state == "3"


async def test_inactive_mac_stays_tracked(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    clients = default_clients()
    del clients[CLIENT_INACTIVE_MAC]
    mock_client.async_get_data.return_value = make_data(clients=clients)
    await _poll(hass, freezer)
    assert hass.states.get("device_tracker.device_02").state == STATE_NOT_HOME
