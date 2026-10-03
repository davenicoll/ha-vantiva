# Vantiva gateway for Home Assistant

A Home Assistant custom integration for Vantiva (formerly Technicolor) gateways that run the
Homeware web interface. It logs in to the gateway's local web GUI, polls a handful of status
pages and exposes LAN client presence, WAN status, GPON optics and system health as entities.
Everything stays on your LAN; no cloud service is involved.

## Supported devices

| Device | Firmware | Status |
|---|---|---|
| Vantiva/Technicolor NH20T (Telus fibre hub, hardware GCNT-K) | Homeware 20.3.i | Verified |
| Other Homeware 20 gateways | Homeware 20.x | Likely to work, untested |

*Verified against NH20T firmware 20.3.i.0565.17 (Home Assistant 2026.9.x)*

Older Homeware 17/18 gateways (DGA, TG789 and similar) use the same login scheme but a different
page layout. They may partly work; reports are welcome.

## Entities

All entities except the device trackers belong to one device representing the gateway.

**Sensors**

| Entity | Notes |
|---|---|
| WAN IPv4 address | |
| Last boot | Timestamp derived from uptime. Changes of less than 60 s are ignored. |
| Connected clients | Clients the gateway currently reports as active |
| Known clients | All clients in the gateway's device list, active or not |
| WAN received / WAN sent | Byte counters, `total_increasing`, shown in GB by default |
| CPU usage, Memory usage | Diagnostic |
| Firmware version, Hardware version | Diagnostic |
| DNS servers, WAN gateway | Diagnostic |
| GPON receive power, GPON transmit power | dBm. Only created when the gateway has a GPON page. |
| GPON transceiver temperature, laser bias current, supply voltage | Diagnostic. GPON gateways only. |

**Binary sensors**

| Entity | Notes |
|---|---|
| Internet | On when the gateway reports the WAN as connected |
| WAN link | Physical WAN link. Only created if the gateway reports it. |
| GPON link | GPON status. Only created if the gateway reports it. |

**Device trackers**

One `device_tracker` entity per MAC address in the gateway's client list. The state is `home`
while the gateway reports the client as active, and for the "consider home" period afterwards.
Attributes: IP address, MAC address, hostname, connection type, interface, port, link speed, SSID
and DHCP vendor class. Clients that first appear after setup are added automatically. Trackers are
not attached to the gateway device; Home Assistant links them to an existing device with the same
MAC address if another integration knows it.

## Installation

### HACS (custom repository)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=davenicoll&repository=ha-vantiva&category=integration)

Or manually in HACS:

1. Open HACS and choose the three-dot menu, then **Custom repositories**.
2. Enter `https://github.com/davenicoll/ha-vantiva`, select the **Integration** type and choose
   **Add**.
3. Search for **Vantiva** in HACS and download it.
4. Restart Home Assistant.

Home Assistant 2026.3.0 or later is required.

### Manual

Copy `custom_components/vantiva` from this repository (or from `vantiva.zip` on a release) into
the `custom_components` directory of your Home Assistant configuration and restart.

## Configuration

Go to **Settings > Devices & services > Add integration** and choose **Vantiva**. The form asks
for:

| Field | Description |
|---|---|
| Host | Gateway address, for example `192.168.1.254`. `http://` or `https://` and a port are accepted. |
| Username | Web interface user, usually `admin` |
| Password | Web interface password, often printed on the gateway label |

The integration logs in once to check the credentials and reads the gateway's MAC address, which
is used to stop the same gateway being added twice.

### Options

After setup, choose **Configure** on the integration entry:

| Option | Default | Description |
|---|---|---|
| Polling interval | 30 s | How often the gateway is polled. Minimum 10 s. |
| Consider home | 180 s | How long a tracker stays `home` after the gateway stops reporting the client as active. |

Changing options reloads the integration.

## Removal

Delete the integration entry under **Settings > Devices & services > Vantiva**. The integration
logs out of the gateway when it is unloaded. If you installed through HACS, remove the repository
there as well and restart Home Assistant.

## Known limitations

- **One web session at a time.** The gateway allows only one logged-in session. Logging in to the
  web GUI in a browser logs the integration out, and the integration logs in again on its next
  poll, which in turn ends the browser session. Expect to be logged out of the GUI within one
  polling interval while the integration is running. Disable the integration entry temporarily if
  you need a long GUI session.
- **No Wi-Fi data on the NH20T.** This model has no Wi-Fi radio, so all clients are reported as
  wired. Gateways with Wi-Fi should report the band and SSID, but this is untested.
- **No reboot button.** The NH20T firmware has no reboot action in its web interface, and the
  integration does not send commands it cannot verify. The integration is read-only.
- Presence is only as accurate as the gateway's device list. Devices that sleep their network
  interface may show as away.

## Troubleshooting

**"The gateway has temporarily locked the account"**: Homeware locks the account for a while after
several failed logins. The integration never retries a rejected password, so the lock comes from
earlier attempts (yours or the integration's before you changed the password). Wait the number of
seconds shown, then try again with the correct password.

**Repeated re-authentication requests**: the password stored in Home Assistant no longer matches.
Follow the repair notification and enter the current password. If the account is locked at the
time, the integration retries later instead of asking.

**Entities unavailable**: check that the gateway is reachable from the Home Assistant host. Enable
debug logging to see which page failed:

```yaml
logger:
  logs:
    custom_components.vantiva: debug
```

Logs include page names and the host, never the password or session cookies. Diagnostics
(**Download diagnostics** on the integration entry) redact the password, MAC and IP addresses,
hostnames and the serial number.

## Credits

The login is the SRP-6a scheme used by Technicolor/Vantiva Homeware firmware. Earlier work on
these gateways includes [shaiu/technicolor](https://github.com/shaiu/technicolor) and the
`pytechnicolor` library ([shaiu/techicolorgateway](https://github.com/shaiu/techicolorgateway)). This integration is a new implementation; [docs/RESEARCH.md](docs/RESEARCH.md)
explains what changed on Homeware 20 and why the earlier integration fails there.

This project is not affiliated with Vantiva or Technicolor.

## Development

```sh
uv venv --python 3.14 .venv
uv pip install -r requirements_test.txt
uv pip install ruff mypy pytest-cov aioresponses
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## License

MIT
