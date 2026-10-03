# Decision records

Decisions made autonomously by the lead agent. Owner: Dave (davenicoll). Dates are absolute.

## ADR-1 (2026-10-03): Build a new `vantiva` integration rather than fork `shaiu/technicolor`

**Context.** The target device is a Vantiva/Technicolor NH20T (Telus GPON fibre hub) on Homeware
20.3.i firmware. Live reproduction (RESEARCH.md §4.2) shows the upstream `pytechnicolor` SRP
login *does* work here; the integration fails afterwards because the published package needs
`lxml` without declaring it, parses `device-modal.lp` with Homeware 17/18 selectors that no
longer match, infers presence from "has an IP" (wrong on this firmware, which keeps stale IPs),
and has a config flow that never validates credentials. The library repository is archived, built
on synchronous RoboBrowser + Werkzeug 0.16.1, and the integration is device-tracker only with
open deprecation and setup bugs and an unanswered modernisation PR.

**Decision.** New integration, domain `vantiva`, with its own aiohttp client that parses the
embedded JSON device arrays, keeps the table parser as a fallback for older pages, and adds WAN,
GPON and system sensors. The upstream findings are written up in RESEARCH.md §4.4 so an issue/PR
can still be filed against `shaiu/technicolor` and `shaiu/techicolorgateway`.

**Consequences.** We own the SRP implementation and parsers. The client stays HA-free so it can be
published to PyPI later.

## ADR-2 (2026-10-03): Credentials never enter the repo

`.env` (gitignored) holds host/user/password for local live tests; all scripts read environment
variables. Fixtures under `tests/fixtures/` are produced by `scripts`-style scrubbing (MACs,
hostnames, public IPs, serial replaced with consistent fakes; CSRF tokens zeroed; log viewer
output not kept). A grep-based leak check runs before each commit.

## ADR-3 (2026-10-03): Read-only against the live router

Research and validation only issue GET requests plus the SRP login/logout POSTs. No settings are
changed, no reboot is triggered, and `broadband-modal.lp` is never requested again because it
terminated the connection on this firmware.

## ADR-4 (2026-10-03): Vendor the client library inside `custom_components/vantiva/vantiva_client`

HACS installs one directory tree; a PyPI dependency would need a release pipeline before v0.1.
The package imports only `aiohttp` and the standard library and contains no HA imports, so it
can be extracted later. `manifest.json` therefore has an empty `requirements` list.

## ADR-5 (2026-10-03): No BeautifulSoup/lxml requirement

The pages are small and regular (`label.control-label` + `.controls`, one JSON array per
client type, one striped table). Standard-library `html.parser` plus regex is sufficient and
avoids pulling a new requirement into HA.

## ADR-6 (2026-10-03): No reboot button in v0.1

The NH20T GUI exposes no reboot action (no `gateway-modal.lp`, no `action=reboot` form in
`system-info-modal.lp`). Posting an unverified action to the live router violates ADR-3. Revisit
if a user with a Homeware 20 device that has the reboot card can test it.

## ADR-7 (2026-10-03): Polling defaults

Scan interval 30 s (configurable, minimum 10 s). Each poll fetches five small pages plus the
~280 KB `device-modal.lp`; measured well under one second on the LAN. `consider_home` default
180 s for device trackers, matching HA's legacy default.

## ADR-8 (2026-10-03): Python 3.14, minimum Home Assistant 2026.3.0

Home Assistant core requires Python >= 3.14.2 (verified in `home-assistant/core` dev
`pyproject.toml`); the latest stable release is 2026.9.4. Tooling targets `py314`. `hacs.json`
sets `homeassistant: "2026.3.0"` so the bundled `brand/` icon directory is honoured and users on
releases from the last six months can install. Local dev uses the Homebrew `python3.14`.

## ADR-7 amendment (2026-10-03): default poll interval is 5 minutes

Dave asked for a 5-minute default. `DEFAULT_SCAN_INTERVAL` is now 300 s (minimum still 10 s,
configurable in options). Rationale beyond the request: the router allows a single web session,
so less frequent polling also means fewer forced logouts of anyone using the gateway's own GUI.
`consider_home` stays at 180 s; with a 300 s poll a client that disappears is reported away at the
next poll. Shipped as v0.1.1.
