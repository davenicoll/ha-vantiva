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

### 2. Home Assistant Integration Test

**Status:** Run by lead (see below)

The Home Assistant Docker end-to-end test is being executed by the team lead in a non-sandboxed environment with the HA image already available locally.

**Test Coverage:**
- [ ] Container startup and onboarding via REST API
- [ ] Config flow with router credentials
- [ ] Entity creation (sensors, binary_sensors, device_tracker)
- [ ] Entity state validation
- [ ] Diagnostics endpoint (password/MAC redaction)
- [ ] HA log monitoring (no errors/warnings)
- [ ] Coordinator polling (3+ cycles)
- [ ] Options flow (scan interval change)

**Results:** (to be filled by lead)

## Findings

### Issues Found
None identified in live client testing.

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
