# Client API contract

Package: `custom_components/vantiva/vantiva_client` (pure Python 3.14, `aiohttp` only, no Home
Assistant imports). The integration layer and the client are developed in parallel against this
contract; changes to it must be made here first.

```python
from custom_components.vantiva.vantiva_client import (
    VantivaClient, VantivaData, GatewayInfo, WanStatus, GponStats, LanClient,
    VantivaError, VantivaConnectionError, VantivaAuthError, VantivaLockedOutError,
    VantivaParseError,
)
```

## Exceptions (`exceptions.py`)

```
VantivaError(Exception)                     # base
├── VantivaConnectionError                  # DNS/TCP/timeout/HTTP 5xx/connection reset
├── VantivaAuthError                        # router rejected credentials or returned {"error":...}
│   └── VantivaLockedOutError(wait_seconds: int | None, wrong_count: int | None)
└── VantivaParseError                       # page fetched but expected structure missing
```

## Models (`models.py`) — all `@dataclass(frozen=True, slots=True)`

```python
class ConnectionType(StrEnum):
    WIRED = "wired"; WIFI_2G = "wifi_2g"; WIFI_5G = "wifi_5g"; WIFI_6G = "wifi_6g"
    WIFI_GUEST_2G = "wifi_guest_2g"; WIFI_GUEST_5G = "wifi_guest_5g"; MOCA = "moca"; UNKNOWN = "unknown"

class LanClient:
    mac: str                      # normalised lower-case "aa:bb:cc:dd:ee:ff"
    hostname: str | None          # HostName (None if empty)
    friendly_name: str | None     # FriendlyName (None if empty or same as hostname)
    ip: str | None                # IPv4 (None if empty)
    ipv6: str | None
    active: bool                  # State == "1" (JSON) or status LED "green" (table)
    connection: ConnectionType    # derived from InterfaceType/Radio/SSID/source array
    interface: str | None         # raw L2Interface, e.g. "eth4"
    port: str | None              # "5"
    speed_mbps: int | None        # Speed
    ssid: str | None
    lease_type: str | None        # "DHCP" | "Static" | ...
    vendor_class: str | None      # DhcpVendorClass
    connected_since: datetime | None   # from ConnectedTime epoch (UTC, tz-aware)
    lease_remaining: timedelta | None

class GatewayInfo:
    vendor: str | None; product: str | None; serial: str | None
    software_version: str | None; firmware_version: str | None; hardware_version: str | None
    mac: str | None               # normalised lower-case
    uptime: timedelta | None      # parsed from "49 days 22 hours 3 minutes 52 seconds"
    memory_pct: int | None; cpu_pct: int | None; reboot_cause: str | None

class WanStatus:
    connected: bool               # internet-modal Status == "Connected"
    ipv4: str | None; ipv6: str | None; gateway: str | None
    dns: tuple[str, ...]          # split on ","
    lease_obtained: datetime | None; lease_expires: datetime | None   # naive router-local time -> tz-aware UTC not assumed; store as naive
    link_up: bool | None          # diagnostics "WAN Available" == "Link Up"
    gpon_up: bool | None          # diagnostics "GPON Status" == "Up"
    rx_bytes: int | None; tx_bytes: int | None    # internet-modal "Bytes": value with icon-download = received, icon-upload = transmitted
    rx_packets: int | None; tx_packets: int | None
    rx_errors: int | None; tx_errors: int | None

class GponStats:
    bandwidth_up_mbps: int | None; bandwidth_down_mbps: int | None
    wavelength_up_nm: int | None; wavelength_down_nm: int | None
    transceiver_type: str | None
    tx_power_dbm: float | None; rx_power_dbm: float | None
    bias_ma: float | None; vcc_v: float | None; temperature_c: float | None

class VantivaData:
    gateway: GatewayInfo
    wan: WanStatus
    gpon: GponStats | None        # None when the gpon-overview page is unavailable
    clients: dict[str, LanClient] # keyed by mac
    fetched_at: datetime          # UTC
    @property
    def active_client_count(self) -> int
```

## Client (`client.py`)

```python
class VantivaClient:
    def __init__(
        self,
        host: str,                       # "192.168.1.254", "192.168.1.254:8080", "http://…", "https://…" all accepted
        username: str,
        password: str,
        session: aiohttp.ClientSession,  # caller-owned; the client never closes it
        *,
        request_timeout: float = 15.0,
        verify_ssl: bool = True,
    ) -> None

    @property
    def base_url(self) -> str            # normalised "http://192.168.1.254" (no trailing slash)
    @property
    def is_authenticated(self) -> bool

    async def async_login(self) -> None
        # Full SRP flow (ARCHITECTURE.md). Raises VantivaAuthError / VantivaLockedOutError /
        # VantivaConnectionError. Retries exactly once on HTTP 403 (stale CSRF) with a fresh token.
        # Never retries after an auth error. Stores the post-login CSRF token.

    async def async_logout(self) -> None
        # POST / do_signout=1 + CSRFtoken. Swallows errors; always clears local auth state.

    async def async_get_gateway_info(self) -> GatewayInfo
    async def async_get_wan_status(self) -> WanStatus
    async def async_get_gpon_stats(self) -> GponStats | None     # None if page 404
    async def async_get_clients(self) -> dict[str, LanClient]
        # device-modal.lp JSON arrays first; if none found, ipv6devices-modal.lp table.
    async def async_get_data(self) -> VantivaData
        # Fetches the pages above concurrently (asyncio.gather) after ensuring login.

    async def async_test_connection(self) -> GatewayInfo
        # login + gateway info; used by the config flow.
```

Behaviour rules:

* Every page fetch goes through one `_async_fetch_page(path)` that: ensures a login exists;
  GETs; if the body contains `id="srp_password"` (login page) or status is 401/403, logs in again
  **once** and refetches; maps aiohttp errors to `VantivaConnectionError`.
* The client never requests `/modals/broadband-modal.lp` and never POSTs anything except the two
  SRP steps and the logout.
* Debug logs must not include the password, `A`, `M`, salts, or cookies. Log the host and page
  names only.
* SRP randomness from `secrets`. The SRP module exposes `SrpClient(username, password)` with
  `start() -> A_hex`, `process_challenge(salt_hex, B_hex) -> M_hex`, `verify(M2_hex) -> bool`
  so it can be unit-tested with fixed `a` (allow injecting `a` for tests).

## Test fixtures

`tests/fixtures/nh20t/*.html` are scrubbed live captures. Key values the tests can assert:

| Fixture | Expectation |
|---|---|
| `system-info-modal.html` | product "NH20T", vendor "Technicolor", hardware "GCNT-K", software "20.3.i.0565.17", uptime 49 d 22 h 3 m 52 s, memory 54, cpu 2, reboot cause "User Initiated", mac "02:00:00:00:00:26" |
| `internet-modal.html` | connected True, ipv4 "203.0.113.58", gateway "203.0.113.1", dns ("198.51.100.67","198.51.100.116"), rx_bytes 3939997125741, tx_bytes 1393232473707 (the page shows the transmit value first, marked with an upload icon; values are assigned by icon, not position) |
| `gpon-overview-modal.html` | bandwidth 10000/10000, wavelength 1270/1577, tx 6.5236239, rx -17.544872, temp 40.597656 |
| `diagnostics-connection-modal.html` | link_up True, gpon_up True, ipv4 "203.0.113.58", ipv6 None ("No Address Assigned") |
| `device-modal.html` | 36 ethernet clients, all `ConnectionType.WIRED`, mix of active True/False, first client hostname "device-01" ip "192.168.1.117" mac "02:00:00:00:00:02" port "5" speed 2500 |
| `ipv6devices-modal.html` | 37 rows; status LED `light green` → active, `light off` → inactive |
| `login.html` | CSRF token meta present (64 hex chars) |
| `home.html` | post-login page; `#wan_ip` "203.0.113.58" |
