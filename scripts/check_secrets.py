#!/usr/bin/env python3
"""Fail if router secrets or identifying data appear in tracked (or staged) files.

Usage: scripts/check_secrets.py [--staged]

Checks (never prints secret values):
1. No .env file (other than .env.example) is tracked/staged.
2. No identifying patterns: a real VANTIVA_PASSWORD assignment, 64-hex sessionID cookies,
   the operator's public IP ranges observed on the test device.
3. Fixtures only contain synthetic MAC addresses (02:00:00:00:xx:xx).
4. Every password/secret/token value from the local untracked .env is absent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SKIP = {".env.example", "scripts/check_secrets.py"}
GENERIC = [
    (re.compile(rb"VANTIVA_PASSWORD=(?!changeme)\S+"), "VANTIVA_PASSWORD assignment"),
    (re.compile(rb"sessionID=[0-9a-f]{64}"), "router session cookie"),
    (re.compile(rb"\b216\.232\.\d{1,3}\.\d{1,3}\b"), "operator public IP (216.232/16)"),
    (re.compile(rb"\b75\.153\.\d{1,3}\.\d{1,3}\b"), "operator public IP (75.153/16)"),
]
MAC_RE = re.compile(rb"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")
SYNTHETIC_MAC = re.compile(rb"^02:00:00:00:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}$")


def listed_files(staged: bool) -> list[Path]:
    cmd = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
        if staged
        else ["git", "ls-files"]
    )
    out = subprocess.check_output(cmd, cwd=ROOT, text=True)
    return [ROOT / f for f in out.splitlines() if f and f not in SKIP and (ROOT / f).is_file()]


def env_values() -> list[tuple[str, bytes]]:
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip("'\"")
        # Only secret-like keys; the username is the firmware default shown on the login page.
        if not val or not re.search(r"PASS|SECRET|TOKEN|KEY", key, re.I):
            continue
        values.append((key.strip(), val.encode()))
    return values


def main() -> int:
    staged = "--staged" in sys.argv
    files = listed_files(staged)
    secrets = env_values()
    problems: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        name = path.name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            problems.append(f"{rel}: env file must not be committed")
        data = path.read_bytes()
        for pattern, label in GENERIC:
            if pattern.search(data):
                problems.append(f"{rel}: {label}")
        if rel.startswith("tests/fixtures/"):
            bad = {m.group(0) for m in MAC_RE.finditer(data) if not SYNTHETIC_MAC.match(m.group(0))}
            if bad:
                problems.append(f"{rel}: {len(bad)} non-synthetic MAC address(es)")
        for key, val in secrets:
            if val in data:
                problems.append(f"{rel}: contains the value of {key} from .env")
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    print(f"check_secrets: clean ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
