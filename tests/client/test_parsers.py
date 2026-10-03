"""Parser tests against the scrubbed NH20T captures plus synthetic edge cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from custom_components.vantiva.vantiva_client import ConnectionType, VantivaParseError
from custom_components.vantiva.vantiva_client.parsers import (
    is_login_page,
    normalise_mac,
    parse_control_fields,
    parse_csrf_token,
    parse_device_modal,
    parse_duration,
    parse_gateway_info,
    parse_gpon_stats,
    parse_home_wan_ip,
    parse_lan_clients_table,
    parse_wan_status,
)
from tests.client.fake_router import fixture

# --------------------------------------------------------------------------------------------
# Fixture expectations (docs/CLIENT_API.md table)
# --------------------------------------------------------------------------------------------


def test_system_info_fixture() -> None:
    info = parse_gateway_info(fixture("system-info-modal.html"))
    assert info.product == "NH20T"
    assert info.vendor == "Technicolor"
    assert info.hardware_version == "GCNT-K"
    assert info.software_version == "20.3.i.0565.17"
    assert info.firmware_version == "20.3.i.0565-4629006-20260217054338.17"
    assert info.serial == "CP0000000000"
    assert info.uptime == timedelta(days=49, hours=22, minutes=3, seconds=52)
    assert info.memory_pct == 54
    assert info.cpu_pct == 2
    assert info.reboot_cause == "User Initiated"
    # The contract table says 02:00:00:00:00:01; the scrubbed capture actually holds :26.
    assert info.mac == "02:00:00:00:00:26"


def test_internet_fixture() -> None:
    wan = parse_wan_status(fixture("internet-modal.html"))
    assert wan.connected is True
    assert wan.ipv4 == "203.0.113.58"
    assert wan.gateway == "203.0.113.1"
    assert wan.dns == ("198.51.100.67", "198.51.100.116")
    assert wan.lease_obtained == datetime(2026, 10, 3, 9, 21, 41)
    assert wan.lease_expires == datetime(2026, 10, 3, 13, 21, 41)
    assert wan.lease_obtained.tzinfo is None
    # Values are assigned by the GUI's direction icons: icon-download = received.
    assert wan.rx_bytes == 3939997125741
    assert wan.tx_bytes == 1393232473707
    assert {wan.rx_bytes, wan.tx_bytes} == {1393232473707, 3939997125741}
    assert wan.rx_packets == 3129767977
    assert wan.tx_packets == 1475545718
    assert wan.rx_errors == 0
    assert wan.tx_errors == 0
    # Without the diagnostics page these are unknown.
    assert wan.link_up is None
    assert wan.gpon_up is None
    assert wan.ipv6 is None


def test_internet_plus_diagnostics_fixture() -> None:
    wan = parse_wan_status(
        fixture("internet-modal.html"), fixture("diagnostics-connection-modal.html")
    )
    assert wan.link_up is True
    assert wan.gpon_up is True
    assert wan.ipv4 == "203.0.113.58"
    assert wan.ipv6 is None


def test_diagnostics_fixture_values() -> None:
    fields = parse_control_fields(fixture("diagnostics-connection-modal.html"))
    assert fields["wan available"].text == "Link Up"
    assert fields["gpon status"].text == "Up"
    assert fields["ip version 4 address"].text == "203.0.113.58"
    assert fields["ip version 6 address"].text == "No Address Assigned"
    assert "icon-ok icon-large green" in fields["wan available"].classes


def test_gpon_fixture() -> None:
    gpon = parse_gpon_stats(fixture("gpon-overview-modal.html"))
    assert gpon is not None
    assert gpon.bandwidth_up_mbps == 10000
    assert gpon.bandwidth_down_mbps == 10000
    assert gpon.wavelength_up_nm == 1270
    assert gpon.wavelength_down_nm == 1577
    assert gpon.transceiver_type == "DIPLEXER"
    assert gpon.tx_power_dbm == pytest.approx(6.5236239)
    assert gpon.rx_power_dbm == pytest.approx(-17.544872)
    assert gpon.bias_ma == pytest.approx(12.368)
    assert gpon.vcc_v == pytest.approx(3.2248001)
    assert gpon.temperature_c == pytest.approx(40.597656)


def test_device_modal_fixture() -> None:
    clients = parse_device_modal(fixture("device-modal.html"))
    assert clients is not None
    assert len(clients) == 36
    assert all(c.connection is ConnectionType.WIRED for c in clients.values())
    states = {c.active for c in clients.values()}
    assert states == {True, False}
    assert sum(c.active for c in clients.values()) == 31
    first = next(iter(clients.values()))
    assert first.mac == "02:00:00:00:00:02"
    assert clients["02:00:00:00:00:02"] is first
    assert first.hostname == "device-01"
    assert first.friendly_name is None  # identical to hostname
    assert first.ip == "192.168.1.117"
    assert first.ipv6 is None
    assert first.port == "5"
    assert first.speed_mbps == 2500
    assert first.interface == "eth4"
    assert first.lease_type == "DHCP"
    assert first.vendor_class == "android-dhcp-17"
    assert first.ssid is None
    assert first.connected_since == datetime.fromtimestamp(1790986117, UTC)
    assert first.lease_remaining == timedelta(seconds=70710)
    assert {c.lease_type for c in clients.values()} == {"DHCP", "Static"}
    assert all(mac == mac.lower() for mac in clients)


def test_ipv6devices_fixture() -> None:
    now = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
    clients = parse_lan_clients_table(fixture("ipv6devices-modal.html"), now=now)
    assert len(clients) == 37
    assert sum(c.active for c in clients.values()) == 31
    assert sum(not c.active for c in clients.values()) == 6
    first = clients["02:00:00:00:00:02"]
    assert first.active is True
    assert first.hostname == "device-01"
    assert first.ip == "192.168.1.117"
    assert first.interface == "Ethernet Port5"
    assert first.port == "5"
    assert first.connection is ConnectionType.WIRED
    assert first.connected_since == now - timedelta(hours=16, minutes=22, seconds=32)
    assert first.lease_remaining == timedelta(hours=19, minutes=37, seconds=27)
    inactive = clients["02:00:00:00:00:04"]
    assert inactive.active is False
    assert inactive.ip is None
    assert inactive.connected_since is None
    assert inactive.lease_remaining is None
    # "Infinity" lease
    assert clients["02:00:00:00:00:07"].lease_remaining is None


def test_login_fixture() -> None:
    html = fixture("login.html")
    token = parse_csrf_token(html)
    assert token is not None
    assert len(token) == 64
    assert all(ch in "0123456789abcdef" for ch in token)
    assert is_login_page(html)


def test_home_fixture() -> None:
    html = fixture("home.html")
    assert parse_home_wan_ip(html) == "203.0.113.58"
    assert not is_login_page(html)
    assert parse_csrf_token(html) is not None


@pytest.mark.parametrize(
    "name",
    [
        "system-info-modal.html",
        "internet-modal.html",
        "gpon-overview-modal.html",
        "device-modal.html",
        "ipv6devices-modal.html",
        "home.html",
    ],
)
def test_data_pages_are_not_login_pages(name: str) -> None:
    assert not is_login_page(fixture(name))


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("49 days 22 hours 3 minutes 52 seconds", timedelta(days=49, seconds=79432)),
        ("1 day 1 second", timedelta(days=1, seconds=1)),
        ("3 minutes", timedelta(minutes=3)),
        ("16 hours 22 minutes 32 seconds", timedelta(hours=16, minutes=22, seconds=32)),
        ("  2 Hours\n 5 Seconds ", timedelta(hours=2, seconds=5)),
        ("5 min 3 sec", timedelta(minutes=5, seconds=3)),
        ("1d 2h 3m 4s", timedelta(days=1, hours=2, minutes=3, seconds=4)),
        ("3600", timedelta(hours=1)),
        ("0 seconds", timedelta(0)),
        ("-", None),
        ("", None),
        ("Infinity", None),
        (None, None),
    ],
)
def test_parse_duration(text: str | None, expected: timedelta | None) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("02:00:00:00:00:01", "02:00:00:00:00:01"),
        ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
        ("aa-bb-cc-dd-ee-ff", "aa:bb:cc:dd:ee:ff"),
        ("aabb.ccdd.eeff", "aa:bb:cc:dd:ee:ff"),
        ("AABBCCDDEEFF", "aa:bb:cc:dd:ee:ff"),
        ("a:b:c:d:e:f", "0a:0b:0c:0d:0e:0f"),
        (" 02:00:00:00:00:01 ", "02:00:00:00:00:01"),
        ("zz:bb:cc:dd:ee:ff", None),
        ("aa:bb:cc:dd:ee", None),
        ("", None),
        ("-", None),
        (None, None),
        (12, None),
    ],
)
def test_normalise_mac(value: object, expected: str | None) -> None:
    assert normalise_mac(value) == expected


def test_csrf_token_attribute_order_and_missing() -> None:
    assert parse_csrf_token("<meta content='abc' name='CSRFtoken'>") == "abc"
    assert parse_csrf_token('<meta name="other" content="x">') is None
    assert parse_csrf_token('<meta name="CSRFtoken" content="">') is None
    assert parse_csrf_token("<html></html>") is None


def test_login_page_detection_variants() -> None:
    assert is_login_page('<input id="srp_password">')
    assert is_login_page("<input id = 'srp_password' type=password>")
    assert not is_login_page('<input id="srp_password1">')
    assert not is_login_page("")


def test_home_wan_ip_missing() -> None:
    assert parse_home_wan_ip("<p>nothing</p>") is None
    assert parse_home_wan_ip('<strong id="wan_ip">No IP</strong>') is None


# --------------------------------------------------------------------------------------------
# Control-field edge cases
# --------------------------------------------------------------------------------------------


def _group(label: str, controls: str) -> str:
    return (
        f'<div class="control-group"><label class="control-label">{label}</label>'
        f'<div class="controls">{controls}</div></div>'
    )


def test_control_fields_nested_and_whitespace() -> None:
    html = (
        _group(" Product\n  Name ", '<span class="x"><b> NH20T </b>\n<br/><br></span>')
        + _group("", "<input value='hidden'>")
        + _group("Product Name", "second wins? no")
        + '<label class="control-label">Orphan</label>'
    )
    fields = parse_control_fields(html)
    assert fields["product name"].text == "NH20T"
    assert "" not in fields
    assert "orphan" not in fields


def test_control_fields_unterminated_controls_still_recorded() -> None:
    html = '<label class="control-label">Status</label><div class="controls"><span>Connected'
    assert parse_control_fields(html)["status"].text == "Connected"


def test_control_fields_entities_and_void_controls() -> None:
    html = (
        _group("Bandwidth(Up&#47;Down) [Mbps/Mbps]", "1000&#47;500")
        + '<label class="control-label">Void</label><input class="controls" value="1">'
    )
    fields = parse_control_fields(html)
    assert fields["bandwidth(up/down) [mbps/mbps]"].text == "1000/500"
    assert fields["void"].text == ""  # void element as .controls: recorded, no text
    gpon = parse_gpon_stats(html)
    assert gpon is not None
    assert gpon.bandwidth_up_mbps == 1000
    assert gpon.bandwidth_down_mbps == 500
    assert gpon.wavelength_up_nm is None


def test_system_info_missing_structure_raises() -> None:
    with pytest.raises(VantivaParseError):
        parse_gateway_info("<html><body>nothing</body></html>")
    with pytest.raises(VantivaParseError):
        parse_gateway_info(_group("Unrelated", "x"))


def test_system_info_partial_and_odd_values() -> None:
    html = (
        _group("Product Name", "NH20T")
        + _group("Uptime", "5 minutes")
        + _group("Memory Usage", "n/a")
        + _group("CPU Usage", " 7% ")
        + _group("MAC Address", "not-a-mac")
    )
    info = parse_gateway_info(html)
    assert info.product == "NH20T"
    assert info.uptime == timedelta(minutes=5)
    assert info.memory_pct is None
    assert info.cpu_pct == 7
    assert info.mac is None
    assert info.vendor is None


def test_internet_missing_structure_raises() -> None:
    with pytest.raises(VantivaParseError):
        parse_wan_status("<p>empty</p>")


def test_wan_units_without_icons_and_bad_values() -> None:
    html = (
        _group("Status", '<div class="light red"></div>Disconnected')
        + _group("IPv4 address", "No Address Assigned")
        + _group("Gateway", "")
        + _group("DNS servers", "198.51.100.1, bogus ,2001:db8::1")
        + _group("Lease obtained", "not a date")
        + _group("Bytes", "10 Bytes 20 Bytes")
        + _group("Packets", "5 Pkd")
        + _group("Errors", "-")
    )
    wan = parse_wan_status(
        html, _group("WAN Available", "Link Down") + _group("GPON Status", "Down")
    )
    assert wan.connected is False
    assert wan.ipv4 is None
    assert wan.gateway is None
    assert wan.dns == ("198.51.100.1", "2001:db8::1")
    assert wan.lease_obtained is None
    assert wan.lease_expires is None
    # GUI order without icons: upload (tx) first, then download (rx).
    assert (wan.tx_bytes, wan.rx_bytes) == (10, 20)
    assert (wan.tx_packets, wan.rx_packets) == (5, None)
    assert (wan.rx_errors, wan.tx_errors) == (None, None)
    assert wan.link_up is False
    assert wan.gpon_up is False


def test_wan_download_icon_first() -> None:
    html = _group("Status", "Connected") + _group(
        "Bytes",
        '<i class="icon-download"></i> 1,234 Bytes <i class="icon-upload"></i> 99 Bytes',
    )
    wan = parse_wan_status(html)
    assert wan.rx_bytes == 1234
    assert wan.tx_bytes == 99


def test_wan_ipv6_from_diagnostics() -> None:
    wan = parse_wan_status(
        _group("Status", "Connected"),
        _group("IP Version 4 Address", "192.0.2.1")
        + _group("IP Version 6 Address", "2001:db8::5 fe80::1"),
    )
    assert wan.ipv4 == "192.0.2.1"
    assert wan.ipv6 == "2001:db8::5"


def test_gpon_page_without_gpon_fields_returns_none() -> None:
    assert parse_gpon_stats(_group("Something", "else")) is None
    assert parse_gpon_stats("") is None


# --------------------------------------------------------------------------------------------
# Device arrays
# --------------------------------------------------------------------------------------------


def _device_page(**arrays: list[dict[str, object]]) -> str:
    script = "\n".join(f"var {name} = {json.dumps(items)};" for name, items in arrays.items())
    return f"<html><script>\n{script}\n</script></html>"


def test_device_modal_without_arrays_returns_none() -> None:
    assert parse_device_modal("<html>old firmware</html>") is None


def test_device_modal_empty_arrays_return_empty_dict() -> None:
    assert parse_device_modal(_device_page(ethernet_data=[], wifi2_data=[])) == {}


def test_device_modal_connection_mapping_and_dedupe() -> None:
    page = _device_page(
        ethernet_data=[
            {"MACAddress": "AA:AA:AA:AA:AA:01", "State": "1", "InterfaceType": "ethernet"},
            {"MACAddress": "AA:AA:AA:AA:AA:02", "State": "1", "InterfaceType": "moca"},
            {"MACAddress": "", "State": "1"},
            {"MACAddress": "garbage", "State": "1"},
            "not a dict",
            {"MACAddress": "aa:aa:aa:aa:aa:05", "State": "0", "HostName": "dup"},
        ],
        wifi2_data=[
            {
                "MACAddress": "aa:aa:aa:aa:aa:03",
                "State": "1",
                "SSID": "Home",
                "HostName": "phone",
                "FriendlyName": "My Phone",
                "IPAddress": "192.168.1.3 2001:db8::3",
                "Speed": "",
                "ConnectedTime": "0",
                "LeaseTimeRemaining": "-1",
            }
        ],
        wifi5_data=[{"MACAddress": "aa:aa:aa:aa:aa:04", "State": 1}],
        guest_wifi2_data=[{"MACAddress": "aa:aa:aa:aa:aa:06", "State": "1"}],
        guest_wifi5_data=[
            {"MACAddress": "aa:aa:aa:aa:aa:07", "State": "1"},
            {"MACAddress": "aa:aa:aa:aa:aa:05", "State": "1", "HostName": "dup-active"},
        ],
        wifi6_data=[{"MACAddress": "aa:aa:aa:aa:aa:08", "State": "1"}],
        mystery_data=[
            {"MACAddress": "aa:aa:aa:aa:aa:09", "InterfaceType": "wireless", "Radio": "radio_5G"},
            {"MACAddress": "aa:aa:aa:aa:aa:0a", "InterfaceType": "ethernet"},
            {"MACAddress": "aa:aa:aa:aa:aa:0b", "InterfaceType": "wireless", "Radio": "2.4GHz"},
            {"MACAddress": "aa:aa:aa:aa:aa:0c", "InterfaceType": "wireless", "Radio": "6 GHz"},
            {"MACAddress": "aa:aa:aa:aa:aa:0d", "InterfaceType": "wireless"},
            {"MACAddress": "aa:aa:aa:aa:aa:0e"},
        ],
        guest_mystery_data=[
            {"MACAddress": "aa:aa:aa:aa:aa:0f", "InterfaceType": "wireless", "Radio": "radio2"},
        ],
    )
    clients = parse_device_modal(page)
    assert clients is not None
    c = {mac[-2:]: client for mac, client in clients.items()}
    assert c["01"].connection is ConnectionType.WIRED
    assert c["01"].mac == "aa:aa:aa:aa:aa:01"
    assert c["02"].connection is ConnectionType.MOCA
    assert c["03"].connection is ConnectionType.WIFI_2G
    assert c["03"].ssid == "Home"
    assert c["03"].friendly_name == "My Phone"
    assert c["03"].ip == "192.168.1.3"
    assert c["03"].ipv6 == "2001:db8::3"
    assert c["03"].speed_mbps is None
    assert c["03"].connected_since is None
    assert c["03"].lease_remaining is None
    assert c["04"].connection is ConnectionType.WIFI_5G
    assert c["04"].active is True  # numeric State
    assert c["05"].hostname == "dup-active"  # active duplicate replaces inactive one
    assert c["06"].connection is ConnectionType.WIFI_GUEST_2G
    assert c["07"].connection is ConnectionType.WIFI_GUEST_5G
    assert c["08"].connection is ConnectionType.WIFI_6G
    assert c["09"].connection is ConnectionType.WIFI_5G
    assert c["0a"].connection is ConnectionType.WIRED
    assert c["0b"].connection is ConnectionType.WIFI_2G
    assert c["0c"].connection is ConnectionType.WIFI_6G
    assert c["0d"].connection is ConnectionType.UNKNOWN
    assert c["0e"].connection is ConnectionType.UNKNOWN
    assert c["0f"].connection is ConnectionType.WIFI_GUEST_2G
    assert c["0e"].active is False
    assert len(clients) == 15


def test_device_modal_inactive_duplicate_does_not_replace_active() -> None:
    page = _device_page(
        ethernet_data=[{"MACAddress": "aa:aa:aa:aa:aa:01", "State": "1", "HostName": "a"}],
        wifi2_data=[{"MACAddress": "aa:aa:aa:aa:aa:01", "State": "0", "HostName": "b"}],
    )
    clients = parse_device_modal(page)
    assert clients is not None
    assert clients["aa:aa:aa:aa:aa:01"].hostname == "a"


def test_device_modal_string_containing_bracket_semicolon() -> None:
    items = [{"MACAddress": "aa:aa:aa:aa:aa:01", "HostName": "evil];name", "State": "1"}]
    page = f"<script>var ethernet_data = {json.dumps(items)};</script>"
    clients = parse_device_modal(page)
    assert clients is not None
    assert clients["aa:aa:aa:aa:aa:01"].hostname == "evil];name"


def test_device_modal_broken_json_is_skipped() -> None:
    page = (
        "<script>var ethernet_data = [{broken];\n"
        'var wifi2_data = [{"MACAddress": "aa:aa:aa:aa:aa:01", "State": "1"}];</script>'
    )
    clients = parse_device_modal(page)
    assert clients is not None
    assert list(clients) == ["aa:aa:aa:aa:aa:01"]


def test_device_modal_non_list_and_bad_epoch() -> None:
    page = (
        '<script>var meta_data = [1, 2];var x_data = {"a": 1};'
        'var ethernet_data = [{"MACAddress": "aa:aa:aa:aa:aa:01", '
        '"ConnectedTime": "99999999999999999"}];</script>'
    )
    clients = parse_device_modal(page)
    assert clients is not None
    assert clients["aa:aa:aa:aa:aa:01"].connected_since is None


# --------------------------------------------------------------------------------------------
# Client table
# --------------------------------------------------------------------------------------------

_HEADER = (
    "<thead><tr><th>Status</th><th>Hostname</th><th>IPv4</th><th>MAC Address</th>"
    "<th>Interface</th><th>Connected Time</th><th>Expires In</th><th>IPv6</th>"
    "<th>IPv6 Link Local Addr</th></tr></thead>"
)


def _row(status: str, host: str, ip: str, mac: str, iface: str, ipv6: str = "") -> str:
    return (
        f'<tr><td><span><div class="{status}"></div></span></td><td>{host}</td><td>{ip}</td>'
        f"<td>{mac}</td><td>{iface}</td><td>1 hours</td><td>-</td><td>{ipv6}</td>"
        "<td>fe80::1</td></tr>"
    )


def test_table_parser_edge_cases() -> None:
    html = (
        "<table><tr><td>layout table</td></tr></table>"
        f"<table>{_HEADER}<tbody>"
        + _row(
            "light green", "a", "192.168.1.2", "AA-AA-AA-AA-AA-01", "Wireless - 5GHz", "2001:db8::2"
        )
        + _row("light orange", "b", "", "aa:aa:aa:aa:aa:02", "WiFi 2.4GHz Guest")
        + _row("light off", "c", "", "not-a-mac", "Ethernet Port1")
        + _row("light off", "dup", "", "aa:aa:aa:aa:aa:01", "Ethernet Port1")
        + _row("light green", "m", "", "aa:aa:aa:aa:aa:03", "MoCA")
        + _row("light green", "x", "", "aa:aa:aa:aa:aa:04", "Something")
        + "<tr><td>short row</td></tr>"
        + "</tbody></table>"
    )
    clients = parse_lan_clients_table(html)
    assert len(clients) == 4
    a = clients["aa:aa:aa:aa:aa:01"]
    assert a.hostname == "a"
    assert a.active is True
    assert a.connection is ConnectionType.WIFI_5G
    assert a.ipv6 == "2001:db8::2"
    assert a.port is None
    assert a.connected_since is not None
    b = clients["aa:aa:aa:aa:aa:02"]
    assert b.active is False
    assert b.connection is ConnectionType.WIFI_GUEST_2G
    assert clients["aa:aa:aa:aa:aa:03"].connection is ConnectionType.MOCA
    assert clients["aa:aa:aa:aa:aa:04"].connection is ConnectionType.UNKNOWN


def test_table_without_led_uses_status_text() -> None:
    html = (
        "<table><tr><th>State</th><th>Name</th><th>IP Address</th><th>MAC</th></tr>"
        "<tr><td>Active</td><td>n</td><td>192.168.1.9</td><td>aa:aa:aa:aa:aa:01</td></tr>"
        "<tr><td>Inactive</td><td>m</td><td></td><td>aa:aa:aa:aa:aa:02</td></tr></table>"
    )
    clients = parse_lan_clients_table(html)
    assert clients["aa:aa:aa:aa:aa:01"].active is True
    assert clients["aa:aa:aa:aa:aa:01"].ip == "192.168.1.9"
    assert clients["aa:aa:aa:aa:aa:01"].connection is ConnectionType.UNKNOWN
    assert clients["aa:aa:aa:aa:aa:02"].active is False


def test_headerless_table_uses_default_layout() -> None:
    html = "<table>" + _row(
        "light green", "a", "192.168.1.2", "aa:aa:aa:aa:aa:01", "Ethernet Port2"
    )
    clients = parse_lan_clients_table(html)  # unterminated table is closed by the parser
    assert clients["aa:aa:aa:aa:aa:01"].port == "2"
    assert clients["aa:aa:aa:aa:aa:01"].connection is ConnectionType.WIRED


def test_table_missing_raises() -> None:
    with pytest.raises(VantivaParseError):
        parse_lan_clients_table("<p>no table</p>")
    with pytest.raises(VantivaParseError):
        parse_lan_clients_table("<table><tr><td>x</td></tr></table>")


def test_empty_table_with_header_is_empty_dict() -> None:
    assert parse_lan_clients_table(f"<table>{_HEADER}<tbody></tbody></table>") == {}
