"""Generate translations/en.json from strings.json by resolving common HA keys."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vantiva"

COMMON = {
    "[%key:common::config_flow::data::host%]": "Host",
    "[%key:common::config_flow::data::username%]": "Username",
    "[%key:common::config_flow::data::password%]": "Password",
    "[%key:common::config_flow::error::cannot_connect%]": "Failed to connect",
    "[%key:common::config_flow::error::invalid_auth%]": "Invalid authentication",
    "[%key:common::config_flow::error::unknown%]": "Unexpected error",
    "[%key:common::config_flow::abort::already_configured_device%]": "Device is already configured",
    "[%key:common::config_flow::abort::reauth_successful%]": "Re-authentication was successful",
}


def _resolve(value):
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, str) and value.startswith("[%key:"):
        return COMMON[value]
    return value


def main() -> None:
    strings = json.loads((ROOT / "strings.json").read_text())
    out = ROOT / "translations" / "en.json"
    out.write_text(json.dumps(_resolve(strings), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
