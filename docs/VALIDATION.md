# Live Validation Results

**Date:** 2026-10-03  
**Tester:** validator-live agent  
**Environment:** macOS Darwin 25.6.0, Docker Desktop  
**Repository:** /Users/dave/Source/davenicoll/ha-vantiva  
**Branch:** docs/live-validation

## Test Environment

### Router Hardware
- **Model:** Technicolor NH20T (hardware GCNT-K)
- **Firmware:** 20.3.i.0565-4629006-20260217054338.17
- **Software Version:** 20.3.i.0565.17
- **Uptime:** 49 days, 22:58:31
- **Network:** GPON (10000/10000 Mbps)

### Test Infrastructure
- **Live Client Test:** Docker container (`python:3.14-slim`)
- **Dependencies:** aiohttp, homeassistant (for integration imports)
- **Network Access:** Docker containers can reach LAN (macOS host cannot due to local-network privacy)
- **Security:** Credentials from `.env` file, never printed or logged

## Test Results

### 1. Live Client Test ✓ PASSED

**Command:**
```bash
docker run --rm -v "$PWD":/app -w /app --env-file .env \
  python:3.14-slim sh -c \
  "pip install -q aiohttp homeassistant && python scripts/live_probe.py"
```

**Results:**

#### Gateway Information
- Product: NH20T ✓
- Firmware: 20.3.i.0565.17 ✓
- Serial/MAC: Present ✓

#### WAN Status
- Connected: True ✓
- Link Up: True ✓
- GPON Up: True ✓
- IPv4 Address: Present (redacted) ✓
- IPv6 Address: Not configured
- Gateway: Present ✓
- DNS Servers: 2 configured ✓

#### GPON Statistics
- Bandwidth: 10000/10000 Mbps up/down ✓
- Wavelength: 1270/1577 nm ✓
- Transceiver: DIPLEXER ✓
- TX Power: 6.5328975 dBm ✓
- RX Power: -18.096684 dBm ✓
- Bias Current: 12.396 mA ✓
- Voltage: 3.2212 V ✓
- Temperature: 40.597656°C ✓

#### LAN Clients
- Total Clients: 36 ✓
- Active Clients: 30 ✓
- Inactive Clients: 6 ✓
- Connection Types: All wired (port 5, 2500 Mbps) ✓
- IPv6 Devices Table: 37 rows ✓

Sample clients (MACs redacted):
```
Pixel-6                26:xx:xx:xx:xx:b2  active=True   wired  port=5  speed=2500
wled-GITHUB-WLED       88:xx:xx:xx:xx:18  active=True   wired  port=5  speed=2500  
32TCLRokuTV            00:xx:xx:xx:xx:af  active=False  wired  port=5  speed=2500
```

#### Session Management
- Login: Successful ✓
- Data Fetch: Complete ✓
- Logout: True ✓

**Validation Checks:**
- [x] Gateway product is NH20T
- [x] WAN connected
- [x] WAN link up
- [x] GPON stats present
- [x] Clients found (>0)
- [x] Active/inactive client mix
- [x] Logout succeeded

**Full output:** See `docs/validation/live-client-test.txt`

### 2. Home Assistant Integration Test ✓ PASSED

**Run by:** lead agent, 2026-10-03, on the host (Docker Desktop), after the live client test.

**Environment**
- `ghcr.io/home-assistant/home-assistant:stable` (2026.9.x), fresh `/config` with `custom_components/vantiva` copied in (not bind-mounted).
- Onboarding, config flow, options flow and diagnostics driven through the REST API from the host (`/usr/bin/python3`, credentials read from the untracked `.env` via environment variables, nothing printed).
- Screenshots taken with Playwright (Chromium, 1440×900) after logging in through the normal login form with a throwaway test user. Public IPs, serial number and MAC addresses were masked in the images before saving.
- The container, its `/config` directory (which holds the router password in `.storage/core.config_entries`) and all temporary files were deleted afterwards.

**Results**

| Check | Result |
|---|---|
| Container startup, onboarding via REST | ✓ `/api/onboarding/users`, `core_config`, `analytics`, `integration` all 200 |
| Integration discovered by HA loader | ✓ "We found a custom integration vantiva" (expected warning for custom integrations) |
| Config flow `user` step | ✓ form with `host`, `username`, `password`; submit → `create_entry`, title **NH20T**, entry state `loaded` |
| Entities created | ✓ 56: 36 `device_tracker` (27 home / 9 not_home at first poll, 30 / 6 after the router updated its table), 17 `sensor`, 3 `binary_sensor` |
| Binary sensors | ✓ `binary_sensor.nh20t_internet` = on, `nh20t_wan_link` = on, `nh20t_gpon_link` = on |
| Sensors | ✓ WAN IPv4 / gateway / DNS present (redacted), connected clients 27→30, known clients 36, CPU 2 %, memory 54 %, firmware `20.3.i.0565-…17`, hardware GCNT-K, last boot 2026-08-14 (stable across polls), GPON Rx −18.3 dBm / Tx 6.5 dBm / 41.0 °C / 12.4 mA / 3.23 V, WAN received 3944.7 GB / sent 1394.6 GB (increasing between polls) |
| Coordinator polling | ✓ values changed at 18:21:42 and 18:22:44 (30 s interval); entry stayed `loaded` |
| Diagnostics (`/api/diagnostics/config_entry/<id>`) | ✓ password `**REDACTED**`, 0 unredacted public IPs, 0 unredacted MACs, password string absent from the whole payload |
| Options flow | ✓ form with `scan_interval`, `consider_home`; set 60 s / 180 s → `create_entry`, entry reloaded and `loaded` |
| HA log (`docker logs`) | ✓ no WARNING/ERROR from `custom_components.vantiva`; only the standard "not been tested by Home Assistant" notice and an unrelated `rich` SyntaxWarning from HA's own dependencies |

**Screenshots** (`docs/screenshots/`, redacted)

| File | Shows |
|---|---|
| `01-integrations.png` | Integrations dashboard with the Vantiva card ("1 device") and bundled brand icon |
| `02-integration-entry.png` | Vantiva entry page: version 0.1.0, 1 device, 56 entities, hub NH20T |
| `03-gateway-device.png` | NH20T device page: device info (firmware, hardware), sensors, diagnostics, activity |
| `04-config-flow.png` | "Connect to a Vantiva gateway" config flow dialog (host, username, password) |

**Notes**
- `device_tracker` home count moved from 27 to 30 within a minute: the router's own `State` flag flaps for a few clients, which is the source of truth the integration reports. `consider_home` (default 180 s) smooths this in HA.
- The first attempt to open the config flow dialog via the `/config/integrations/dashboard/add?domain=vantiva` deep link rendered nothing in headless Chromium; clicking "Add hub" on the entry page worked.

## Findings

### Issues Found
None identified in the live client test or the Home Assistant end-to-end test.

### Observations
1. **Client Data Quality:** All 36 LAN clients discovered successfully
2. **GPON Telemetry:** Full optical statistics available
3. **Connection Stability:** Router session maintained without issues
4. **Data Parsing:** All parsers handled live data correctly
5. **Session Management:** Single-session constraint respected (login/logout cycle successful)

## Security Validation

✓ **Credentials:** Never printed, logged, or exposed  
✓ **Router Access:** Read-only operations only  
✓ **Session Limit:** Respected one-session-at-a-time constraint  
✓ **MAC Addresses:** Redacted in all outputs  
✓ **IP Addresses:** Public IPs redacted

## Entities Created

_(To be populated after HA integration test)_

## Recommendations

1. **Production Ready:** Client library successfully handles live router communication
2. **Data Coverage:** Comprehensive gateway, WAN, GPON, and client data extraction
3. **Error Handling:** No exceptions during normal operation
4. **Resource Usage:** Minimal router load (single poll cycle completed quickly)

## Conclusion

The vantiva_client library has been successfully validated against live NH20T hardware. All core functionality works correctly:
- Gateway detection and information extraction
- WAN connectivity status and statistics
- GPON optical telemetry
- LAN client discovery and state tracking
- Proper session management

The Home Assistant integration layer validation is being completed by the team lead.

---

**Test Artifacts:**
- `docs/validation/live-client-test.txt` - Full live probe output
- `docs/validation/diagnostics.redacted.json` - (pending HA test)
- `docs/screenshots/` - (pending HA test)
