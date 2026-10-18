PHASE: COMPLETE

# STATUS

Project: ha-vantiva — Home Assistant custom integration (domain `vantiva`) for Vantiva/Technicolor Homeware gateways.
Repo: https://github.com/davenicoll/ha-vantiva (public since 2026-10-03). Release: https://github.com/davenicoll/ha-vantiva/releases/tag/v0.1.0 (with `vantiva.zip`).

## Done
- Phase 1 research (docs/RESEARCH.md): router identified live as Vantiva/Technicolor NH20T (Telus GPON fibre hub, Homeware 20.3.i.0565, no Wi-Fi); SRP-6a login reverse-engineered and reproduced; all data pages captured; scrubbed fixtures. Root cause of the upstream `shaiu/technicolor` failure found by live reproduction: its SRP works, but the published `pytechnicolor` needs `lxml` without declaring it (crash → "Error setting up entry"), its selectors target Homeware 17/18, presence is inferred from "has IP", and the config flow never validates credentials. ADR-1: new integration rather than fork; upstream findings written up for an issue/PR.
- Phase 2 (docs/ARCHITECTURE.md, docs/CLIENT_API.md, docs/DECISIONS.md ADR-1..8, docs/PUBLISHING.md): Python 3.14, HA ≥ 2026.3.0, vendored aiohttp client, no extra requirements.
- Phase 3 build (PRs #1, #2, #4): client library (SRP, parsers, models; 143 tests, 99 % coverage) and integration (config flow + reauth + options, coordinator, device_tracker, sensor, binary_sensor, diagnostics, translations, icons, quality_scale.yaml, bundled brand, hacs.json, workflows, README). Combined: 171 tests pass, ruff + mypy clean.
- Phase 4 validation (PR #3 review → #4, PR #5 live): independent Sonnet review (3 minor fixes); live client test against the router passed; Home Assistant 2026.9 in Docker end-to-end passed (config flow → NH20T entry, 56 entities, diagnostics redacted, 3+ polls, options flow, clean log); redacted screenshots in docs/screenshots/ and report in docs/VALIDATION.md.
- Captain request: representative screenshot at the top of README.md (PR #6).
- Secrets: `.env` untracked; history audited; `scripts/check_secrets.py` + gitleaks run locally as pre-commit (staged) and pre-push (full history) hooks per Dave; no CI secrets scan (too late by then).
- v0.1.0 released; v0.1.1 released (PR #7): default poll interval 5 min, allowed range 60 s to 86400 s per Dave; gitleaks moved from CI into the local hooks (PR #8).
- Dave's pre-publication request: full-history gitleaks scan run locally (gitleaks 8.30, 30 commits, no leaks; only the untracked `.env` is flagged in a working-tree scan). Safe to make public from a secrets standpoint.

## CI on main
- Test (ruff, mypy, pytest), hassfest and the HACS action (all 9 checks) pass. Secrets checks run locally only (pre-commit/pre-push hooks).

## Standing orders
- Model policy (Dave via fleet captain, 2026-10-18): Claude Opus 5.5 (Bedrock `us.anthropic.claude-opus-5-5`, Agent tool `model: opus`) for ALL development, build, implementation, data-pull, formatting and other mechanical subagents. Claude Fable 5.1 (`us.anthropic.claude-fable-5-1`) ONLY for design, architecture, requirements, review/verification, red-team and judgment roles; the project lead stays on Fable. In-flight work is not killed; builders switch at their next spawn. (Validators must still differ from the model that wrote the code: use Sonnet or Fable to review Opus-built code.)
- CI guidance (Dave via captain, 2026-10-13; Actions freeze lifted): batch commits so each PR triggers CI once, no rapid repeated pushes; fix flaky CI instead of re-running (failures bill minutes). When the captain confirms a self-hosted runner label for this repo, open a small PR switching every workflow `runs-on` to `[self-hosted, linux, asura]`, adding a `concurrency` group with `cancel-in-progress: true`, and `paths` filters so docs-only changes skip CI. Do not push that PR before the label is confirmed. Caveat flagged to captain: this repo is PUBLIC; GitHub advises against self-hosted runners on public repos (fork PRs can run code on the runner), so the switch may need to stay on hosted runners or be limited to push events on main.
- PR size (Dave, 2026-10-12): every PR must aim for under 1000 changed lines; split larger work into stacked or sequential PRs. Exceed only when unavoidable, and then say so in the PR description and tell the captain. Pass this rule to every builder/teammate spawned.

## Blockers / decisions for Dave
- Repo is public; HACS default-list submission is now possible (checklist in docs/PUBLISHING.md). Until accepted, install as a HACS custom repository.
- Reboot button not implemented: the NH20T GUI exposes no reboot action (ADR-6).
- Upstream issue for shaiu/technicolor not filed (needs Dave's account); text is ready in docs/RESEARCH.md §4.4.

## Next (optional)
- File the upstream issue; submit to hacs/default after going public; replace the generated purple "V" brand icon with official artwork if desired.
