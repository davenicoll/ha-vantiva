"""Diagnostics tests."""

from __future__ import annotations

import json

from custom_components.vantiva.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from .conftest import HOST, PASSWORD
from .factories import CLIENT_ACTIVE_MAC, GATEWAY_MAC


async def test_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry, snapshot: SnapshotAssertion
) -> None:
    result = await async_get_config_entry_diagnostics(hass, init_integration)

    dumped = json.dumps(result)
    for secret in (PASSWORD, HOST, GATEWAY_MAC, CLIENT_ACTIVE_MAC, "device-01", "203.0.113.58"):
        assert secret not in dumped
    assert "CP0000000000" not in dumped
    assert result == snapshot
