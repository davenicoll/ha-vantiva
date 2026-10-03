# STATUS

PHASE: 3 - Build (in progress)

## Done
- Phase 1 research complete and committed: router identified (Vantiva/Technicolor NH20T, Telus GPON hub, Homeware 20.3.i, no Wi-Fi); SRP-6a login reverse-engineered and reproduced; all data pages captured; scrubbed fixtures in `tests/fixtures/nh20t/`.
- Root cause of the upstream `shaiu/technicolor` failure established by live reproduction (docs/RESEARCH.md §4): its SRP login works, but the published `pytechnicolor` package needs `lxml` without declaring it (crash -> "Error setting up entry"), its `device-modal.lp` selectors do not match Homeware 20, presence is inferred from "has IP" (wrong here), and the config flow never validates credentials.
- ADR-1: new `vantiva` integration (not a fork). ADR-2..8 in docs/DECISIONS.md.
- docs/ARCHITECTURE.md, docs/PUBLISHING.md (HACS, hassfest, brands, quality scale; Python 3.14 verified), docs/CLIENT_API.md (contract between client and integration).
- Private GitHub repo created: github.com/davenicoll/ha-vantiva, main pushed.

## In progress
- `feature/client` (opus dev agent): async SRP client + parsers + aioresponses tests + live probe via Docker.
- `feature/integration` (opus dev agent): config flow, coordinator, device_tracker/sensor/binary_sensor, diagnostics, HACS metadata, workflows, README, pytest-homeassistant-custom-component tests.

## Blockers
- None. Environment notes: host Python builds (uv/pyenv/Homebrew) cannot reach the LAN (macOS local-network privacy); live tests run in Docker (`python:3.14-slim` can reach the router).

## Next
- Review + merge both PRs, run the combined test suite, hassfest/HACS validation.
- Phase 4: sonnet/fable validators; live client test; HA in Docker end-to-end; tag v0.1.0 + release.
