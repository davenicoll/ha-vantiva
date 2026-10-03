# STATUS

PHASE: 4 - Validation (in progress)

## Done
- Phase 1 research (docs/RESEARCH.md): NH20T identified, SRP-6a reproduced, upstream root cause found by live reproduction (undeclared lxml dependency, Homeware 17/18 selectors, presence from IP, no credential validation).
- Phase 2 architecture (docs/ARCHITECTURE.md, docs/CLIENT_API.md), ADR-1..8 (docs/DECISIONS.md), HACS publishing guide (docs/PUBLISHING.md).
- Phase 3 build merged to main: PR #2 client library (SRP, parsers, models; 143 tests, 99% coverage; live probe OK via Docker) and PR #1 integration (config flow + reauth + options, coordinator, device_tracker, sensor, binary_sensor, diagnostics, strings, icons, quality_scale.yaml, hacs.json, brand/, workflows, README; 28 tests). Combined suite: 171 passed, ruff + mypy clean on Python 3.14.
- Secrets guard: scripts/check_secrets.py + pre-commit hook + CI workflow; history audited, clean.
- GitHub repo description/topics set.

## In progress
- Validator A (sonnet): independent code review + test/lint run + CI (hassfest, HACS action) triage; fixes via PR.
- Validator B (sonnet): live validation against the router (read-only) and Home Assistant in Docker end-to-end config flow; screenshots to docs/screenshots.

## Blockers
- HACS default-repo submission needs the repo to be public; HACS custom-repository install works while private only for the owner. Dave's call (see README). Not blocking v0.1.0.

## Next
- Fix validator findings, tag v0.1.0, publish GitHub release with vantiva.zip, final STATUS.
