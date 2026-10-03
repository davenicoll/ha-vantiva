# Research: Vantiva NH20T gateway and existing Technicolor integrations

Date: 2026-10-03. All probing of the live router was read-only (GET requests plus the SRP
login/logout exchange). Credentials are never recorded here; captured pages were scrubbed before
being saved under `tests/fixtures/nh20t/`.

## 1. The device

| Item | Value (from `/modals/system-info-modal.lp`) |
|---|---|
| Product vendor / name | Technicolor **NH20T** (footer: "© Vantiva 2026") |
| Hardware version | GCNT-K |
| Software version | 20.3.i.0565.17 ("Egyptian Blue (20.3.i)" on the home card) |
| Firmware version | 20.3.i.0565-4629006-20260217054338.17 |
| Bootloader | 20.40.1375 |
| Web server | nginx, Lua pages (`*.lp`), Homeware GUI |
| WAN | GPON (fibre), 10000/10000 Mbps, DHCP IPv4, IPv6 disabled |
| Wi-Fi | **None.** No wireless modals; `wifi2_data`/`wifi5_data` arrays are empty |
| LAN | Ethernet (2.5 GbE port 5 in use) and MoCA (LED setting present) |
| Operator | Telus (Canada): French-Canadian language option, Telus-style NH20T "Network Access Hub" |

This is the Homeware 20 generation of the Technicolor/Vantiva gateway firmware. It shares the
login mechanism and page conventions of the Homeware 17/18 DGA/TG789 family that the existing
integrations target, but the page set is different (see 3.3).

## 2. Authentication: SRP-6a over `/authenticate`

`GET /` returns the login page with a `sessionID` cookie (HttpOnly, SameSite=Strict) and
`<meta name="CSRFtoken" content="…64 hex…">`, and loads `/js/srp-min.js` and `/js/login.js`.
Reading the minified SRP code gives the exact protocol, confirmed by a working Python
re-implementation (`scratch/srp_probe.py`, not committed; the production version lives in the
client library):

| Parameter | Value |
|---|---|
| Group | RFC 5054 2048-bit prime, `g = 2` |
| Hash | SHA-256 (jsSHA; the SHA-512 code in the bundle is only used by `sha512crypt` for *setting* passwords) |
| `k` | hard-coded `05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300` = `H(N ‖ pad(g))` |
| `x` | `H(s ‖ H("I:P"))` where `s` is the hex salt string decoded to bytes and the inner hash is decoded from hex |
| `u` | `H(pad256(A) ‖ pad256(B))` |
| `K` | `H(S)` with `S` as minimal big-endian bytes |
| `M1` | `H( (H(N) xor H(g)) ‖ H(I) ‖ s ‖ A ‖ B ‖ K )`; `H(N) xor H(g)` is pre-computed in the JS as `4a76a9a2402bdd18123389b72ebbda50a30f65aedb90d7273130edea4b29cc4c` |
| `M2` | `H(A ‖ M1 ‖ K)` |

Flow:

1. `POST /authenticate` form fields `CSRFtoken`, `I`, `A` (hex) → `{"s":"AF1A0C75","B":"…"}`
   (JSON, uppercase hex, 4-byte salt).
2. `POST /authenticate` form fields `CSRFtoken`, `M` (hex) → `{"M":"…"}` which must equal `M2`
   (compare case-insensitively). Errors come back as `{"error": …}`; a 403 means a stale CSRF
   token and the GUI simply refetches `login.lp` and retries.
3. The GUI then does `GET /login.lp?action=lastaccess` and reloads `/`. The home page now
   has title "Gateway" and a fresh CSRF token.

Observed live:

* Login with the correct credentials succeeds at the first attempt; the server proof verifies.
* **One session at a time.** Logging in again from a second client invalidated the first
  `sessionID` immediately. An idle session was still valid after more than ten minutes.
* Lockout exists: `login.js` reads `waitTime` and `wrongCount` from the error JSON and blocks
  the form (`loginFailureAttempt = true`, `triesbeforemsg = 3`). Clients must not retry a bad
  password.
* `legacySalts`/`userNames` (SHA-1 pre-hash migration path for old accounts) are empty on this
  device, so no SHA-1 step is needed.
* Logout: `POST /` with `do_signout=1` and `CSRFtoken`.
* `GET /gateway.lp?auto_update=true&getSessionStatus=true` → `{"current_role":"admin"}` is a
  cheap session check.

## 3. What the router exposes

### 3.1 Pages that work (all `GET /modals/<name>.lp`, HTML fragments)

| Page | Useful content |
|---|---|
| `system-info-modal` | Product vendor/name, serial, software + firmware version, uptime, hardware version, MAC, memory %, CPU %, reboot cause (`label.control-label` + `span.simple-desc` pairs) |
| `internet-modal` | Status (Connected), IPv4 address, gateway, DNS servers, lease obtained/expires, packet and byte counters (receive / transmit pairs) |
| `gpon-overview-modal` | Bandwidth, wavelengths, optical transceiver type, Tx power (dBm), Rx RSSI (dBm), laser bias (mA), Vcc, temperature |
| `diagnostics-connection-modal` | WAN enable, WAN available ("Link Up"), GPON status ("Up"), IPv4/IPv6 address, DNS/next-hop ping results |
| `device-modal` | ~280 KB visual page. The data is in `<script>` as `var ethernet_data = [...]`, `wifi2_data`, `wifi5_data`, `guest_wifi2_data`, `guest_wifi5_data`: JSON objects with `HostName`, `FriendlyName`, `IPAddress`, `IPv4`, `IPv6`, `MACAddress`, `State` ("1" active / "0" inactive), `InterfaceType`, `L2Interface`, `Port`, `Speed`, `SSID`, `Radio`, `LeaseType`, `DhcpVendorClass`, `ConnectedTime` (epoch), `LeaseTimeRemaining`, byte/packet counters (always 0 here) |
| `ipv6devices-modal` | Same client list as a striped table: status LED (`light green` / `light off`), hostname, IPv4, MAC, interface ("Ethernet Port5"), connected time, lease expiry, IPv6, priority |
| `ethernet-modal` | LAN settings, DHCP server state, static leases table |
| `wanservices-modal` | Port forwarding rules, UPnP state |
| `firewall-modal`, `contentsharing-modal`, `iproutes-modal`, `diagnostics-network-modal`, `diagnostics-ping-modal`, `gpon-cfg-modal`, `booster-modal` (EasyMesh controller row) | Present, not needed for v0.1 |
| `logviewer-modal` | 160 KB syslog; not used, not kept as a fixture |
| `/` (home) | Cards: `#cardSystemVersion`, Broadband "Connected", `#wan_ip`, `#Ethernet_Devices` ("29 Devices"), LAN gateway IP/netmask |

Adding `?auto_update=true` returns the same HTML (no JSON variant). There is no `/api/`,
`/api/v1/` or `/cgi-bin/` (all 404).

### 3.2 Pages that do not work on this firmware

| Page | Result |
|---|---|
| `gateway-modal.lp` (used by Homeware 17/18 for reboot) | 404 |
| `broadband-modal.lp` (DSL stats; used by upstream library) | **Server closes the TCP connection without a response** (twice). Never request it. |
| `wireless-modal.lp`, `wireless-boosters-modal.lp`, `wireless-client-modal.lp`, `lan-modal.lp`, `xdsl-modal.lp`, `tod-modal.lp`, `dmz-modal.lp`, `mmpbx-info-modal.lp`, `qos-modal.lp`, … | 404 |
| `usermgr-modal.lp`, `cwmpconf-modal.lp`, `parental-modal.lp` | Return the login page even when logged in (role-restricted) |

### 3.3 Reboot

No reboot control exists in this GUI: there is no `gateway-modal.lp`, and `system-info-modal.lp`
has no `action=reboot` form. The only references are "scheduleReboot" syslog lines. A reboot
button is therefore out of scope for v0.1 (ADR-6).

## 4. Existing integrations and why they fail here

### 4.1 Inventory

| Project | What | Status (2026-10-03) |
|---|---|---|
| [shaiu/technicolor](https://github.com/shaiu/technicolor) | HACS integration, domain `technicolor`, device_tracker only | Not archived, last push 2025-07-27, 7 open issues, MIT. Open issues: "Error setting up entry" (#22), SSL/URL/deprecated-API bugs (#20), deprecation warnings (#18, #23), missing devices (#15, #16). PR #21 ("Updated to new HA standards, and added ssl support") open since 2026-04 with no response |
| [shaiu/techicolorgateway](https://github.com/shaiu/techicolorgateway) → PyPI `pytechnicolor` 1.1.12 | The scraping library (RoboBrowser + BeautifulSoup + html2text) | **Repository archived** (only Renovate bot PRs since 2024). PyPI release 1.1.12 predates the `get_system_info_modal`/`get_diagnostics_connection_modal` additions (PR #80) that exist in git |
| Ansuel/tch-nginx-gui | Open-source Homeware GUI (reference for `.lp` pages and `srp-min.js`) | Reference only |
| martinellimarco/agthf-router-cli, VulcanusALex/homeware-toolkit | CLI tools for DGA-class routers using the same SRP login | Not HA integrations |

### 4.2 Reproduction against this router

The PyPI package was installed into a clean virtualenv and pointed at the live router (script
`scratch/upstream_repro.py`, not committed, credentials from `.env`):

| Step | Result |
|---|---|
| `srp6authenticate()` | **Succeeds.** Challenge and proof match; the library's SRP parameters (`mysrp.py`: SHA-256, 2048-bit group, hard-coded `k`, `x = H(s ‖ H(I:P))`, `M` with `H(N) xor H(g)`) are identical to what the router's JS does. |
| `get_device_modal()` with the package as published | **Crashes**: `bs4.FeatureNotFound: Couldn't find a tree builder with the features you requested: lxml`. `modal.py` calls `BeautifulSoup(content, features="lxml")` but `setup.py` only declares `six, html2text, robobrowser, Werkzeug==0.16.1`; `lxml` is only in the repo's `requirements.txt`. Home Assistant does not ship lxml, so in HA this is the exception behind "Error setting up entry" (upstream issue #22). |
| `get_device_modal()` after manually installing lxml | Returns 37 devices, but only via the fallback to `ipv6devices-modal.lp`: `device-modal.lp` yields nothing because the parser looks for `div.popUp.smallcard.span4` (capital U, Homeware 17/18) and this firmware uses `popup`, and there is no `<table>`. |
| Same package on Python 3.14 (what HA 2026.x runs) | Imports fine; parsing results identical on the scrubbed fixtures. |

### 4.3 Root causes of "fails with correct credentials"

Ranked by likelihood for this device:

1. **Undeclared `lxml` dependency** makes every device fetch raise. Because
   `TechnicolorRouter.setup()` calls `update_all()` inside `async_setup_entry`, the exception
   aborts the entry with "Error setting up entry" even though the login itself worked.
2. **No credential validation in the config flow.** The flow creates the entry immediately, so
   any problem surfaces later as a setup error that looks like an authentication failure.
3. **Host handling.** The library builds `http://{host}:80`; entering `http://192.168.1.254` or a
   URL with a path produces a malformed URL (upstream issue #20). The HTTPS variants of this GUI
   are also unsupported.
4. **Error masking.** `authenticate()` catches *any* exception from the SRP step, logs
   "Authentication failed", then POSTs `username`/`password` to `/` and reports success on any
   HTTP 200 (the login page). Transport errors are reported as authentication failures and real
   auth failures are reported as success.
5. **Wrong presence semantics for this firmware.** Upstream marks a device "connected" when it
   has an IP. On the NH20T the client table keeps the last IP for inactive devices, so absent
   devices stay "home". The real indicator is the `State` field (JSON) or the status LED cell.
6. **Fragile setup code.** `setup()` *returns* `ConfigEntryNotReady` instead of raising it;
   `_LOGGER.exception("…", e)` has a bad format call; `async_forward_entry_setups` is scheduled
   with `create_task` (HA deprecation, issues #18/#23); the lockout timer means retries after a
   bad attempt return `{"error": …}` with a wait time that the library ignores.
7. **`broadband-modal.lp`.** Not called by the integration itself, but the library exposes it and
   on this firmware the request kills the connection.

The SRP salt/B parameters, password hashing, endpoint paths, CSRF token and HTTPS redirects are
all *not* the problem on this device.

### 4.4 Findings worth filing upstream

* Add `lxml` (or switch to `html.parser`) to `install_requires` in `pytechnicolor`.
* Parse `var ethernet_data = [...]` (and the `wifi*_data` arrays) from `device-modal.lp` on
  Homeware 20; the `popUp` selector no longer matches.
* Use the status column / `State` field for `is_connected`.
* Validate credentials in the config flow, raise `ConfigEntryNotReady`/`ConfigEntryAuthFailed`
  properly, drop the "simple authenticate" fallback, and accept `http(s)://` in the host field.

## 5. Decision

See `docs/DECISIONS.md` ADR-1: build a new `vantiva` integration with its own aiohttp client.
The archived library, its synchronous RoboBrowser/Werkzeug 0.16 stack, the device-tracker-only
scope and the Homeware 17/18 assumptions make a fork more work than a clean implementation
that targets Homeware 20 while keeping the fallbacks (table parser) that also cover older pages.
