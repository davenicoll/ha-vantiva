"""Diagnostics support for the Vantiva integration."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import VantivaConfigEntry

TO_REDACT_CONFIG = {CONF_HOST, CONF_PASSWORD, CONF_USERNAME}
TO_REDACT_DATA = {
    "mac",
    "ip",
    "ipv4",
    "ipv6",
    "gateway",
    "dns",
    "hostname",
    "friendly_name",
    "serial",
}


def _jsonable(value: Any) -> Any:
    """Convert dataclass output to JSON-friendly primitives."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VantivaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data: dict[str, Any] | None = None
    if coordinator.data is not None:
        snapshot = coordinator.data
        data = {
            "gateway_info": _jsonable(dataclasses.asdict(snapshot.gateway)),
            "wan": _jsonable(dataclasses.asdict(snapshot.wan)),
            "gpon": _jsonable(dataclasses.asdict(snapshot.gpon)) if snapshot.gpon else None,
            # Clients are keyed by MAC; emit a list so the keys do not leak.
            "clients": [_jsonable(dataclasses.asdict(c)) for c in snapshot.clients.values()],
            "active_client_count": snapshot.active_client_count,
            "fetched_at": snapshot.fetched_at.isoformat(),
        }
    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(data, TO_REDACT_DATA) if data is not None else None,
    }
