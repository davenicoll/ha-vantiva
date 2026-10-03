# Architecture

This document describes how the `vantiva` Home Assistant integration is built. See
`docs/RESEARCH.md` for what the router exposes and why, and `docs/DECISIONS.md` for
the decision records referenced below (ADR-n).

## Layout

```
ha-vantiva/
├── custom_components/vantiva/          # HA integration (what HACS installs)
│   ├── __init__.py                     # setup/unload, runtime_data, platform forwarding
│   ├── manifest.json
│   ├── const.py
│   ├── config_flow.py                  # user step + reauth + options (scan interval, consider_home)
│   ├── coordinator.py                  # DataUpdateCoordinator -> VantivaData snapshot
│   ├── entity.py                       # base entity with DeviceInfo for the gateway
│   ├── device_tracker.py               # ScannerEntity per LAN client
│   ├── sensor.py                       # WAN IP, uptime, firmware, counts, optics, CPU/mem, traffic
│   ├── binary_sensor.py                # internet connectivity, GPON link, WAN link
│   ├── diagnostics.py                  # redacted config entry + last snapshot
│   ├── strings.json, translations/en.json
│   ├── icons.json
│   └── vantiva_client/                 # vendored async client library (ADR-4)
│       ├── __init__.py
│       ├── srp.py                      # SRP-6a maths mirroring /js/srp-min.js
│       ├── client.py                   # aiohttp session, login/logout, page fetch, retry on 401/login page
│       ├── parsers.py                  # HTML/JS -> dataclasses
│       ├── models.py                   # dataclasses: GatewayInfo, WanStatus, GponStats, LanClient, ...
│       └── exceptions.py
├── tests/
│   ├── fixtures/nh20t/                 # scrubbed real responses from the router
│   ├── client/                         # library unit tests (aioresponses)
│   └── integration/                    # pytest-homeassistant-custom-component tests
├── scripts/live_probe.py               # read-only live check using .env (never in CI)
├── hacs.json, README.md, LICENSE
├── pyproject.toml                      # ruff, mypy, pytest config, dev deps
└── .github/workflows/                  # hassfest, hacs/action, pytest, release zip
```

The client library lives inside the integration package (`custom_components/vantiva/vantiva_client`)
so that HACS installs a single self-contained tree and there is no PyPI release to manage for
v0.1 (ADR-4). The module has no Home Assistant imports and only depends on `aiohttp`, which
HA already ships, so it can be lifted into a standalone PyPI package later without changes.

## Client library

### Authentication (`srp.py`, `client.py`)

The router's login is SRP-6a as implemented by `/js/srp-min.js` (verified live, see RESEARCH.md):

| Parameter | Value |
|---|---|
| Group | RFC 5054 2048-bit, `g = 2` |
| Hash | SHA-256 |
| `k` | constant `05b9e8ef…e300` (the JS hard-codes it; equals `H(N ‖ pad(g))`) |
| `x` | `H(hex(s) ‖ hex(H(I ‖ ":" ‖ P)))`, both halves interpreted as hex bytes |
| `u` | `H(pad256(A) ‖ pad256(B))` |
| `K` | `H(hex(S))` |
| `M1` | `H(uconst ‖ H(I) ‖ s ‖ A ‖ B ‖ K)` where `uconst = H(N) xor H(g)` is the constant `4a76a9a2…cc4c` and all parts are hex strings decoded to bytes |
| `M2` | `H(A ‖ M1 ‖ K)` |

Sequence:

1. `GET /` → `sessionID` cookie and `<meta name="CSRFtoken" content=…>`.
2. `POST /authenticate` form `CSRFtoken, I, A` → JSON `{s, B}`.
3. `POST /authenticate` form `CSRFtoken, M` → JSON `{M}`; verify equals `M2` (case-insensitive).
4. `GET /login.lp?action=lastaccess` (what the GUI does; harmless, kept for parity).
5. Re-read `/` to pick up the post-login CSRF token for later POSTs (logout only).

Error handling: step 2/3 returning `{"error": …}` or a non-JSON body raises `VantivaAuthError`.
A 403 means the CSRF token was stale; the client refreshes it once and retries. The firmware
locks the account after repeated failures (`waitTime` / `wrongCount` in the error JSON), so the
client never retries a failed password and surfaces the wait time in the exception.

Session handling: the router allows **one authenticated session at a time**: a new SRP login
invalidates the previous `sessionID` (verified live). The client therefore logs in once and reuses
the session for as long as it lasts (a session was still valid after 10+ minutes idle); logging in
on every poll would log the user out of the web GUI on every poll, and opening the GUI will in turn
log the integration out, which is handled by the re-login path below. A logged-in `sessionID`
cookie keeps working until the router expires it or another login replaces it.
Every page fetch checks for the login form (`id="srp_password"`) in the response; if found the
client logs in again once and refetches. On unload the integration logs out
(`POST /` with `do_signout=1` and `CSRFtoken`) to free the router's session slot.

### Data sources (`parsers.py`)

| Page | Content used | Parser |
|---|---|---|
| `/modals/system-info-modal.lp` | Product name, serial, software/firmware version, hardware version, MAC, uptime, memory %, CPU %, reboot cause | `.control-group` label → `.controls` text |
| `/modals/internet-modal.lp` | Status, IPv4 address, gateway, DNS servers, lease times, packet/byte counters (rx/tx) | same |
| `/modals/gpon-overview-modal.lp` | Bandwidth, wavelength, Tx power, Rx RSSI, bias, Vcc, temperature | same |
| `/modals/diagnostics-connection-modal.lp` | WAN enable, WAN link, GPON status, IPv4/IPv6 address | same |
| `/modals/device-modal.lp` | `var ethernet_data = […]`, `wifi2_data`, `wifi5_data`, `guest_*` JSON arrays with HostName, IPAddress, MACAddress, State, InterfaceType, Port, Speed, L2Interface, ConnectedTime, LeaseType, DhcpVendorClass, SSID, Radio | regex for `var <name> = [...]` then `json.loads` |
| `/` (home) | `#wan_ip`, `#Ethernet_Devices`, `#cardSystemVersion` | used only as a cheap fallback / connectivity check |

`ipv6devices-modal.lp` has the same client list as a table; it is parsed as a fallback for
firmware that does not embed the JSON arrays.

Only `aiohttp` and the standard library are used. HTML parsing is done with a small
regex/`html.parser` based extractor rather than BeautifulSoup to avoid adding a requirement
(ADR-5). All numeric fields are parsed defensively; missing fields become `None`.

Pages known to be dangerous (`broadband-modal.lp` drops the connection on this firmware) or
absent (`gateway-modal.lp`, wireless modals) are never requested. Page availability is probed
once at setup and cached, so the integration also works on sibling Homeware 20 models that
lack GPON or have Wi-Fi.

### Models (`models.py`)

```python
@dataclass(frozen=True)
class LanClient:
    mac: str            # normalised lower-case aa:bb:cc:dd:ee:ff
    hostname: str | None
    friendly_name: str | None
    ip: str | None
    ipv6: str | None
    active: bool        # State == "1"
    interface_type: str # "ethernet" | "wireless" | "moca" | ...
    connection: str     # "wired" | "wifi_2g" | "wifi_5g" | "wifi_guest_2g" | ... (derived)
    port: str | None
    speed_mbps: int | None
    ssid: str | None
    lease_type: str | None
    vendor_class: str | None
    connected_since: datetime | None

@dataclass(frozen=True)
class GatewayInfo: vendor, product, serial, software_version, firmware_version, hardware_version, mac, uptime: timedelta | None, memory_pct, cpu_pct, reboot_cause
@dataclass(frozen=True)
class WanStatus: connected: bool, ipv4, ipv6, gateway, dns: list[str], lease_obtained, lease_expires, link_up: bool | None, gpon_up: bool | None, rx_bytes, tx_bytes, rx_packets, tx_packets, rx_errors, tx_errors
@dataclass(frozen=True)
class GponStats: bandwidth_up, bandwidth_down, wavelength_up, wavelength_down, tx_power_dbm, rx_power_dbm, bias_ma, vcc_v, temperature_c
@dataclass(frozen=True)
class VantivaData: gateway, wan, gpon, clients: dict[str, LanClient]
```

## Integration layer

* **Config flow**: single `user` step with host, username (default `admin`), password; optional
  "verify SSL"/scheme is not needed (router is HTTP only on the LAN; `https://` host prefix is
  honoured if given). `test-before-configure`: logs in and fetches system info; unique ID is the
  gateway MAC from system info (`unique-config-entry`). Reauth flow on `VantivaAuthError`.
  Options flow: scan interval (default 300 s, 60 s to 86400 s) and `consider_home` seconds for trackers.
* **Coordinator**: one `DataUpdateCoordinator[VantivaData]`; a single `update` fetches the pages
  above concurrently through one aiohttp session, raises `ConfigEntryAuthFailed` on auth errors
  and `UpdateFailed` on transport errors. Page set is fixed after first successful probe.
* **Entities** share `VantivaEntity` with `DeviceInfo(identifiers={(DOMAIN, mac)},
  manufacturer="Vantiva", model=product, sw_version=…, configuration_url=host)`;
  `has_entity_name = True`.
* **device_tracker**: `ScannerEntity` per MAC seen; `is_connected` from `State`; attributes
  hostname, ip, connection type, port, speed, SSID, vendor class. New MACs appearing later are
  added dynamically via a coordinator listener. Trackers default to enabled; the registry keeps
  stale devices like HA core router integrations do.
* **sensor**: WAN IPv4, uptime (timestamp-derived `last_boot`), firmware version
  (diagnostic), connected client count, total client count, GPON Rx/Tx power, temperature,
  CPU %, memory %, WAN rx/tx bytes (`total_increasing`), DNS servers (diagnostic).
* **binary_sensor**: internet connected (`connectivity` class), WAN link up, GPON up.
* **button**: deliberately absent in v0.1 (ADR-6): the Telus NH20T firmware exposes no reboot
  action in its GUI and we will not test an unverified POST against the live device.
* **diagnostics**: config entry with password redacted plus the last `VantivaData` with MACs,
  IPs, hostnames and serial redacted via `async_redact_data`.

## Tooling

* Python 3.14 (Home Assistant core `requires-python >= 3.14.2`, verified 2026-10-03 against
  `home-assistant/core` dev `pyproject.toml`; latest stable HA is 2026.9.4). `pyproject.toml`
  targets `py314` for ruff and mypy (`strict` for the client package). Minimum supported HA in
  `hacs.json` is 2026.3.0 (first release that loads a bundled `brand/` directory).
* Tests: `pytest`, `pytest-asyncio`, `aioresponses` for the client,
  `pytest-homeassistant-custom-component` pinned to a release matching the latest stable HA
  (2026.9.x at time of writing; each release of that package pins one HA version).
* CI: ruff, mypy, pytest, `home-assistant/actions/hassfest`, `hacs/action`.
* Release: tag `vX.Y.Z`, workflow zips `custom_components/vantiva` to `vantiva.zip` and attaches
  it; `manifest.json` version is bumped in the same commit.
