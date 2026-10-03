"""Parsers turning Homeware GUI pages into model objects.

Only the standard library is used (``html.parser`` and ``re``). All numeric fields are parsed
defensively: anything missing or malformed becomes ``None`` rather than raising.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

from .exceptions import VantivaParseError
from .models import ConnectionType, GatewayInfo, GponStats, LanClient, WanStatus

__all__ = [
    "ControlField",
    "is_login_page",
    "normalise_mac",
    "parse_control_fields",
    "parse_csrf_token",
    "parse_device_modal",
    "parse_duration",
    "parse_gateway_info",
    "parse_gpon_stats",
    "parse_home_wan_ip",
    "parse_lan_clients_table",
    "parse_wan_status",
]

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_INT_RE = re.compile(r"[-+]?\d+")
_DURATION_RE = re.compile(
    r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.IGNORECASE
)
_MAC_HEX_RE = re.compile(r"^[0-9a-f]{12}$")
_LOGIN_PAGE_RE = re.compile(r"""id\s*=\s*["']srp_password["']""", re.IGNORECASE)
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_WAN_IP_RE = re.compile(r"""<[^>]*\bid\s*=\s*["']wan_ip["'][^>]*>\s*([^<]*?)\s*<""", re.IGNORECASE)
_JS_ARRAY_RE = re.compile(r"var (\w+_data)\s*=\s*(\[.*?\]);", re.DOTALL)
_JS_ARRAY_START_RE = re.compile(r"var (\w+_data)\s*=\s*(?=\[)")
_WIRED_RE = re.compile(r"\b(?:ethernet|eth\d*|lan\d*|wired)\b")
_PORT_RE = re.compile(r"port\s*(\d+)", re.IGNORECASE)
_EMPTY_VALUES = frozenset({"", "-", "--", "n/a", "na", "none", "null", "unknown"})

_ARRAY_CONNECTION: dict[str, ConnectionType] = {
    "ethernet_data": ConnectionType.WIRED,
    "moca_data": ConnectionType.MOCA,
    "wifi2_data": ConnectionType.WIFI_2G,
    "wifi24_data": ConnectionType.WIFI_2G,
    "wifi5_data": ConnectionType.WIFI_5G,
    "wifi6_data": ConnectionType.WIFI_6G,
    "guest_wifi2_data": ConnectionType.WIFI_GUEST_2G,
    "guest_wifi24_data": ConnectionType.WIFI_GUEST_2G,
    "guest_wifi5_data": ConnectionType.WIFI_GUEST_5G,
    "guest2_data": ConnectionType.WIFI_GUEST_2G,
    "guest5_data": ConnectionType.WIFI_GUEST_5G,
}


# --------------------------------------------------------------------------------------------
# Small value helpers
# --------------------------------------------------------------------------------------------


def _normalise_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _clean(value: object) -> str | None:
    """Return a whitespace-normalised string, or None for empty/placeholder values."""
    if value is None:
        return None
    text = _normalise_ws(str(value))
    if text.lower() in _EMPTY_VALUES:
        return None
    return text


def _to_int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    match = _INT_RE.search(text.replace(",", ""))
    return int(match.group()) if match else None


def _to_float(value: object) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    match = _NUMBER_RE.search(text)
    return float(match.group()) if match else None


def _ip_or_none(value: object, version: int | None = None) -> str | None:
    """Return the first valid IP address in ``value`` (optionally of one version)."""
    text = _clean(value)
    if text is None:
        return None
    for token in re.split(r"[\s,;]+", text):
        try:
            address = ipaddress.ip_address(token.split("%", 1)[0])
        except ValueError:
            continue
        if version is None or address.version == version:
            return token
    return None


def normalise_mac(value: object) -> str | None:
    """Return ``value`` as lower-case ``aa:bb:cc:dd:ee:ff`` or None if it is not a MAC."""
    text = _clean(value)
    if text is None:
        return None
    text = text.lower()
    parts = re.split(r"[:\-]", text)
    if len(parts) == 6 and all(1 <= len(part) <= 2 for part in parts):
        hex_digits = "".join(part.zfill(2) for part in parts)
    else:
        hex_digits = text.replace(".", "")
    if not _MAC_HEX_RE.match(hex_digits):
        return None
    return ":".join(hex_digits[i : i + 2] for i in range(0, 12, 2))


def parse_duration(value: object) -> timedelta | None:
    """Parse strings like ``"49 days 22 hours 3 minutes 52 seconds"`` (any subset of units)."""
    text = _clean(value)
    if text is None:
        return None
    total = 0
    found = False
    for amount, unit in _DURATION_RE.findall(text):
        found = True
        number = int(amount)
        unit_char = unit[0].lower()
        if unit_char == "d":
            total += number * 86400
        elif unit_char == "h":
            total += number * 3600
        elif unit_char == "m":
            total += number * 60
        else:
            total += number
    if not found:
        if text.isdigit():
            return timedelta(seconds=int(text))
        return None
    return timedelta(seconds=total)


def _parse_local_datetime(value: object) -> datetime | None:
    text = _clean(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _epoch_to_datetime(value: object) -> datetime | None:
    seconds = _to_int(value)
    if seconds is None or seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except OverflowError, OSError, ValueError:
        return None


# --------------------------------------------------------------------------------------------
# label.control-label + .controls extraction
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class ControlField:
    """One ``label.control-label`` / ``.controls`` pair.

    ``segments`` keeps the order of nested element classes (``("class", "icon-upload ...")``)
    and text runs (``("text", "123 Bytes")``) so direction icons can be associated with values.
    """

    label: str
    segments: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Return the whitespace-normalised text content of the control."""
        return _normalise_ws(" ".join(value for kind, value in self.segments if kind == "text"))

    @property
    def classes(self) -> list[str]:
        """Return the class attributes of all nested elements, in document order."""
        return [value for kind, value in self.segments if kind == "class"]


def _class_tokens(attrs: Iterable[tuple[str, str | None]]) -> list[str]:
    for name, value in attrs:
        if name == "class" and value:
            return value.split()
    return []


class _ControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: list[ControlField] = []
        self._label_parts: list[str] | None = None
        self._pending_label: str | None = None
        self._current: ControlField | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _class_tokens(attrs)
        if self._current is not None:
            if classes:
                self._current.segments.append(("class", " ".join(classes)))
            if tag not in _VOID_TAGS:
                self._depth += 1
            return
        if tag == "label" and "control-label" in classes:
            self._label_parts = []
            return
        if "controls" in classes and self._pending_label is not None:
            self._current = ControlField(label=self._pending_label)
            self._pending_label = None
            self._depth = 0 if tag in _VOID_TAGS else 1
            if self._depth == 0:
                self._finish()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._current is not None:
            classes = _class_tokens(attrs)
            if classes:
                self._current.segments.append(("class", " ".join(classes)))

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None:
            if tag in _VOID_TAGS:
                return
            self._depth -= 1
            if self._depth <= 0:
                self._finish()
            return
        if tag == "label" and self._label_parts is not None:
            self._pending_label = _normalise_ws("".join(self._label_parts))
            self._label_parts = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            if data.strip():
                self._current.segments.append(("text", data))
        elif self._label_parts is not None:
            self._label_parts.append(data)

    def _finish(self) -> None:
        if self._current is not None and self._current.label:
            self.fields.append(self._current)
        self._current = None
        self._depth = 0

    def close(self) -> None:
        super().close()
        if self._current is not None:
            self._finish()


def parse_control_fields(html: str) -> dict[str, ControlField]:
    """Return ``{lower-case label: ControlField}`` for every labelled control (first wins)."""
    parser = _ControlParser()
    parser.feed(html)
    parser.close()
    result: dict[str, ControlField] = {}
    for item in parser.fields:
        result.setdefault(item.label.lower(), item)
    return result


def _find(fields: Mapping[str, ControlField], *names: str) -> ControlField | None:
    """Look a field up by exact label, then by label prefix (case-insensitive)."""
    wanted = [_normalise_ws(name).lower() for name in names]
    for name in wanted:
        if name in fields:
            return fields[name]
    for name in wanted:
        for label, item in fields.items():
            if label.startswith(name):
                return item
    return None


def _text(fields: Mapping[str, ControlField], *names: str) -> str | None:
    item = _find(fields, *names)
    return _clean(item.text) if item is not None else None


def _directional_pair(item: ControlField | None) -> tuple[int | None, int | None]:
    """Return ``(rx, tx)`` from a control holding upload/download values.

    The GUI marks each value with ``icon-upload`` (sent) or ``icon-download`` (received). If no
    icons are present the GUI order (upload first, then download) is assumed.
    """
    if item is None:
        return None, None
    rx: int | None = None
    tx: int | None = None
    direction: str | None = None
    positional: list[int] = []
    for kind, value in item.segments:
        if kind == "class":
            if "icon-upload" in value.split():
                direction = "tx"
            elif "icon-download" in value.split():
                direction = "rx"
            continue
        for match in _INT_RE.finditer(value.replace(",", "")):
            number = int(match.group())
            if direction == "rx" and rx is None:
                rx = number
            elif direction == "tx" and tx is None:
                tx = number
            elif direction is None:
                positional.append(number)
            direction = None
    if rx is None and tx is None and positional:
        tx = positional[0]
        rx = positional[1] if len(positional) > 1 else None
    return rx, tx


def _split_pair(text: str | None) -> tuple[str | None, str | None]:
    if text is None:
        return None, None
    parts = [part.strip() for part in text.split("/")]
    first = parts[0] if parts else None
    second = parts[1] if len(parts) > 1 else None
    return first, second


def _require_fields(html: str, page: str) -> dict[str, ControlField]:
    fields = parse_control_fields(html)
    if not fields:
        raise VantivaParseError(f"No labelled fields found on {page}")
    return fields


# --------------------------------------------------------------------------------------------
# Page parsers
# --------------------------------------------------------------------------------------------


def is_login_page(html: str) -> bool:
    """Return True if ``html`` is the SRP login form."""
    return bool(_LOGIN_PAGE_RE.search(html))


def parse_csrf_token(html: str) -> str | None:
    """Return the ``<meta name="CSRFtoken">`` content, if present."""
    for meta in _META_RE.findall(html):
        attrs = {
            match.group(1).lower(): match.group(2) if match.group(2) is not None else match.group(3)
            for match in _ATTR_RE.finditer(meta)
        }
        if attrs.get("name", "").lower() == "csrftoken":
            token = attrs.get("content", "").strip()
            return token or None
    return None


def parse_home_wan_ip(html: str) -> str | None:
    """Return the WAN IP shown on the home page card (``#wan_ip``)."""
    match = _WAN_IP_RE.search(html)
    return _ip_or_none(match.group(1)) if match else None


def parse_gateway_info(html: str) -> GatewayInfo:
    """Parse ``/modals/system-info-modal.lp``."""
    fields = _require_fields(html, "system-info-modal")
    info = GatewayInfo(
        vendor=_text(fields, "Product Vendor"),
        product=_text(fields, "Product Name"),
        serial=_text(fields, "Serial Number"),
        software_version=_text(fields, "Software Version"),
        firmware_version=_text(fields, "Firmware Version"),
        hardware_version=_text(fields, "Hardware Version"),
        mac=normalise_mac(_text(fields, "MAC Address")),
        uptime=parse_duration(_text(fields, "Uptime since last reboot", "Uptime")),
        memory_pct=_to_int(_text(fields, "Memory Usage")),
        cpu_pct=_to_int(_text(fields, "CPU Usage")),
        reboot_cause=_text(fields, "Reboot Cause"),
    )
    if info.product is None and info.software_version is None and info.mac is None:
        raise VantivaParseError("system-info-modal has no product, software version or MAC")
    return info


def parse_wan_status(internet_html: str, diagnostics_html: str | None = None) -> WanStatus:
    """Parse ``internet-modal.lp`` plus (optionally) ``diagnostics-connection-modal.lp``."""
    fields = _require_fields(internet_html, "internet-modal")
    diag = parse_control_fields(diagnostics_html) if diagnostics_html else {}

    status = _text(fields, "Status")
    rx_bytes, tx_bytes = _directional_pair(_find(fields, "Bytes"))
    rx_packets, tx_packets = _directional_pair(_find(fields, "Packets"))
    rx_errors, tx_errors = _directional_pair(_find(fields, "Errors"))
    dns_text = _text(fields, "DNS servers", "DNS")
    dns = tuple(
        server
        for server in (_ip_or_none(part) for part in (dns_text or "").split(","))
        if server is not None
    )

    link_text = _text(diag, "WAN Available")
    gpon_text = _text(diag, "GPON Status")

    return WanStatus(
        connected=status is not None and status.lower() == "connected",
        ipv4=_ip_or_none(_text(fields, "IPv4 address"), 4)
        or _ip_or_none(_text(diag, "IP Version 4 Address"), 4),
        ipv6=_ip_or_none(_text(fields, "IPv6 address"), 6)
        or _ip_or_none(_text(diag, "IP Version 6 Address"), 6),
        gateway=_ip_or_none(_text(fields, "Gateway")),
        dns=dns,
        lease_obtained=_parse_local_datetime(_text(fields, "Lease obtained")),
        lease_expires=_parse_local_datetime(_text(fields, "Lease expires")),
        link_up=None if link_text is None else link_text.lower() == "link up",
        gpon_up=None if gpon_text is None else gpon_text.lower() == "up",
        rx_bytes=rx_bytes,
        tx_bytes=tx_bytes,
        rx_packets=rx_packets,
        tx_packets=tx_packets,
        rx_errors=rx_errors,
        tx_errors=tx_errors,
    )


def parse_gpon_stats(html: str) -> GponStats | None:
    """Parse ``gpon-overview-modal.lp``; return None if the page holds no GPON data."""
    fields = parse_control_fields(html)
    bandwidth_up, bandwidth_down = _split_pair(_text(fields, "Bandwidth"))
    wavelength_up, wavelength_down = _split_pair(_text(fields, "Optional Wavelength", "Wavelength"))
    stats = GponStats(
        bandwidth_up_mbps=_to_int(bandwidth_up),
        bandwidth_down_mbps=_to_int(bandwidth_down),
        wavelength_up_nm=_to_int(wavelength_up),
        wavelength_down_nm=_to_int(wavelength_down),
        transceiver_type=_text(fields, "Optical Transceiver Type"),
        tx_power_dbm=_to_float(_text(fields, "Tx Power")),
        rx_power_dbm=_to_float(_text(fields, "Rx RSSI", "Rx Power")),
        bias_ma=_to_float(_text(fields, "Tx Laser Bias", "Laser Bias")),
        vcc_v=_to_float(_text(fields, "Device Vcc", "Vcc")),
        temperature_c=_to_float(_text(fields, "Device Temperature", "Temperature")),
    )
    if stats == GponStats():
        return None
    return stats


# --------------------------------------------------------------------------------------------
# LAN clients
# --------------------------------------------------------------------------------------------


def _wifi_band(text: str) -> str | None:
    lowered = text.lower().replace(" ", "")
    if "6g" in lowered:
        return "6"
    if "5g" in lowered or lowered.endswith("5") or "radio5" in lowered:
        return "5"
    if "2.4" in lowered or "2g" in lowered or lowered.endswith("2") or "radio2" in lowered:
        return "2"
    return None


def _connection_from_text(text: str, *, guest: bool = False) -> ConnectionType:
    lowered = text.lower()
    if "moca" in lowered:
        return ConnectionType.MOCA
    if "guest" in lowered:
        guest = True
    band = _wifi_band(lowered)
    if any(word in lowered for word in ("wireless", "wifi", "wi-fi", "wlan", "radio", "ghz")):
        if band == "6":
            return ConnectionType.WIFI_6G
        if band == "5":
            return ConnectionType.WIFI_GUEST_5G if guest else ConnectionType.WIFI_5G
        if band == "2":
            return ConnectionType.WIFI_GUEST_2G if guest else ConnectionType.WIFI_2G
        return ConnectionType.UNKNOWN
    if _WIRED_RE.search(lowered):
        return ConnectionType.WIRED
    return ConnectionType.UNKNOWN


def _connection_for_item(array_name: str, item: Mapping[str, Any]) -> ConnectionType:
    interface_type = (_clean(item.get("InterfaceType")) or "").lower()
    l2_interface = (_clean(item.get("L2Interface")) or "").lower()
    if "moca" in interface_type or l2_interface.startswith("moca"):
        return ConnectionType.MOCA
    known = _ARRAY_CONNECTION.get(array_name)
    if known is not None:
        return known
    hints = " ".join(
        part
        for part in (interface_type, _clean(item.get("Radio")), array_name.replace("_", " "))
        if part
    )
    return _connection_from_text(hints, guest="guest" in array_name)


def _client_from_json(array_name: str, item: Mapping[str, Any]) -> LanClient | None:
    mac = normalise_mac(item.get("MACAddress"))
    if mac is None:
        return None
    hostname = _clean(item.get("HostName"))
    friendly = _clean(item.get("FriendlyName"))
    ipv4 = None
    for key in ("IPAddress", "IPv4", "DhcpLeaseIP"):
        ipv4 = _ip_or_none(item.get(key), 4)
        if ipv4:
            break
    ipv6 = _ip_or_none(item.get("IPv6"), 6) or _ip_or_none(item.get("IPAddress"), 6)
    lease_seconds = _to_int(item.get("LeaseTimeRemaining"))
    return LanClient(
        mac=mac,
        hostname=hostname,
        friendly_name=None if friendly == hostname else friendly,
        ip=ipv4,
        ipv6=ipv6,
        active=str(item.get("State", "")).strip() == "1",
        connection=_connection_for_item(array_name, item),
        interface=_clean(item.get("L2Interface")),
        port=_clean(item.get("Port")),
        speed_mbps=_to_int(item.get("Speed")),
        ssid=_clean(item.get("SSID")),
        lease_type=_clean(item.get("LeaseType")),
        vendor_class=_clean(item.get("DhcpVendorClass")),
        connected_since=_epoch_to_datetime(item.get("ConnectedTime")),
        lease_remaining=(
            timedelta(seconds=lease_seconds) if lease_seconds and lease_seconds > 0 else None
        ),
    )


def _add_client(clients: dict[str, LanClient], client: LanClient) -> None:
    existing = clients.get(client.mac)
    if existing is None or (client.active and not existing.active):
        clients[client.mac] = client


def _iter_js_arrays(html: str) -> Iterable[tuple[str, list[Any]]]:
    seen: set[str] = set()
    decoder = json.JSONDecoder()
    for match in _JS_ARRAY_RE.finditer(html):
        name = match.group(1)
        try:
            value = json.loads(match.group(2))
        except ValueError:
            continue
        if isinstance(value, list):
            seen.add(name)
            yield name, value
    # Slow path: arrays whose strings contain "];" defeat the lazy regex above.
    for match in _JS_ARRAY_START_RE.finditer(html):
        name = match.group(1)
        if name in seen:
            continue
        try:
            value, _ = decoder.raw_decode(html, match.end())
        except ValueError:
            continue
        if isinstance(value, list):
            seen.add(name)
            yield name, value


def parse_device_modal(html: str) -> dict[str, LanClient] | None:
    """Parse the ``var <name>_data = [...]`` arrays in ``device-modal.lp``.

    Returns None if the page holds no such arrays (older firmware), otherwise the clients keyed
    by MAC. Entries without a valid MAC are skipped; duplicates keep the active entry.
    """
    clients: dict[str, LanClient] = {}
    found = False
    for name, items in _iter_js_arrays(html):
        found = True
        for item in items:
            if not isinstance(item, Mapping):
                continue
            client = _client_from_json(name, item)
            if client is not None:
                _add_client(clients, client)
    return clients if found else None


@dataclass(slots=True)
class _Cell:
    header: bool
    parts: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _normalise_ws(" ".join(self.parts))


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self._table_stack: list[list[list[_Cell]]] = []
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_stack.append([])
        elif not self._table_stack:
            return
        elif tag == "tr":
            self._close_row()
            self._row = []
        elif tag in ("td", "th"):
            self._close_cell()
            if self._row is None:
                self._row = []
            self._cell = _Cell(header=tag == "th")
        elif self._cell is not None:
            classes = _class_tokens(attrs)
            if classes:
                self._cell.classes.append(" ".join(classes))

    def handle_endtag(self, tag: str) -> None:
        if not self._table_stack:
            return
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table":
            self._close_row()
            self.tables.append(self._table_stack.pop())

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.parts.append(data)

    def _close_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append(self._cell)
        self._cell = None

    def _close_row(self) -> None:
        self._close_cell()
        if self._row is not None and self._table_stack:
            self._table_stack[-1].append(self._row)
        self._row = None

    def close(self) -> None:
        super().close()
        while self._table_stack:
            self._close_row()
            self.tables.append(self._table_stack.pop())


def _column_map(header: list[_Cell]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, cell in enumerate(header):
        name = cell.text.lower()
        key: str | None = None
        if "mac" in name:
            key = "mac"
        elif name.startswith("status") or name == "state":
            key = "status"
        elif "host" in name or name == "name":
            key = "hostname"
        elif "ipv6" in name:
            key = None if "link" in name else "ipv6"
        elif "ipv4" in name or name in ("ip", "ip address"):
            key = "ipv4"
        elif "interface" in name:
            key = "interface"
        elif "connected" in name:
            key = "connected"
        elif "expire" in name or "lease" in name:
            key = "expires"
        if key is not None and key not in columns:
            columns[key] = index
    return columns


_DEFAULT_COLUMNS = {
    "status": 0,
    "hostname": 1,
    "ipv4": 2,
    "mac": 3,
    "interface": 4,
    "connected": 5,
    "expires": 6,
    "ipv6": 7,
}


def _client_from_row(
    row: list[_Cell], columns: Mapping[str, int], now: datetime
) -> LanClient | None:
    def cell(key: str) -> _Cell | None:
        index = columns.get(key)
        return row[index] if index is not None and index < len(row) else None

    def text(key: str) -> str | None:
        found = cell(key)
        return _clean(found.text) if found is not None else None

    mac = normalise_mac(text("mac"))
    if mac is None:
        return None
    status_cell = cell("status")
    active = False
    if status_cell is not None:
        for classes in status_cell.classes:
            tokens = classes.split()
            if "light" in tokens:
                active = "green" in tokens
                break
        else:
            active = (_clean(status_cell.text) or "").lower() in ("active", "connected", "1")
    interface = text("interface")
    port_match = _PORT_RE.search(interface or "")
    connected_for = parse_duration(text("connected"))
    return LanClient(
        mac=mac,
        hostname=text("hostname"),
        ip=_ip_or_none(text("ipv4"), 4),
        ipv6=_ip_or_none(text("ipv6"), 6),
        active=active,
        connection=_connection_from_text(interface) if interface else ConnectionType.UNKNOWN,
        interface=interface,
        port=port_match.group(1) if port_match else None,
        connected_since=now - connected_for if connected_for is not None else None,
        lease_remaining=parse_duration(text("expires")),
    )


def parse_lan_clients_table(html: str, now: datetime | None = None) -> dict[str, LanClient]:
    """Parse the client table in ``ipv6devices-modal.lp`` (fallback for older firmware).

    ``now`` (UTC) is used to turn the relative "Connected Time" into ``connected_since``.
    Raises VantivaParseError if the page contains no table with a MAC column.
    """
    now = now or datetime.now(UTC)
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    clients: dict[str, LanClient] = {}
    found = False
    for table in parser.tables:
        columns: dict[str, int] | None = None
        for row in table:
            if row and all(c.header for c in row):
                mapped = _column_map(row)
                if "mac" in mapped:
                    columns = mapped
                continue
            if columns is None:
                # Header-less table: accept it only if it looks like the known layout.
                if len(row) > 3 and normalise_mac(row[3].text):
                    columns = dict(_DEFAULT_COLUMNS)
                else:
                    continue
            client = _client_from_row(row, columns, now)
            if client is not None:
                _add_client(clients, client)
        if columns is not None:
            found = True
    if not found:
        raise VantivaParseError("No client table found on ipv6devices-modal")
    return clients
