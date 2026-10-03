# STATUS

PHASE: 1 - Research (complete, committing)

## Done
- Repo initialised; `.gitignore` covers `.env`, `scratch/`; credentials only in untracked `.env`.
- Router identified live: Vantiva/Technicolor NH20T (Telus GPON hub), Homeware 20.3.i.0565, hardware GCNT-K, no Wi-Fi.
- Auth scheme reverse-engineered from `/js/srp-min.js` and reproduced in Python: SRP-6a, RFC 5054 2048-bit, SHA-256, `/authenticate`. Login succeeds; server proof verified.
- All data modals enumerated and captured; scrubbed fixtures in `tests/fixtures/nh20t/` (leak-checked).
- docs/ARCHITECTURE.md and docs/DECISIONS.md (ADR-1..7) written.

## In progress
- Research agents: upstream Technicolor integrations comparison (RESEARCH.md), HACS publishing (PUBLISHING.md).

## Blockers
- None. Note: uv/pyenv Python cannot reach the LAN on this Mac (macOS local network privacy); live scripts use /usr/bin/python3.

## Next
- Finish RESEARCH.md root-cause write-up, first commit, create GitHub repo.
- Phase 3: client library + integration (opus dev agents), tests, lint.
