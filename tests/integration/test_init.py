"""Setup, unload and coordinator error handling tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from custom_components.vantiva.api import (
    VantivaAuthError,
    VantivaConnectionError,
    VantivaLockedOutError,
    VantivaParseError,
)
from custom_components.vantiva.const import DOMAIN
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .factories import make_data


async def test_setup_and_unload(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    client = entry.runtime_data.client

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    client.async_logout.assert_awaited_once()


@pytest.mark.parametrize(
    "side_effect",
    [VantivaConnectionError("down"), VantivaParseError("bad"), VantivaLockedOutError()],
)
async def test_setup_retry_on_transient_errors(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    side_effect: Exception,
) -> None:
    mock_client.async_get_data.side_effect = side_effect
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.async_get_data.side_effect = VantivaAuthError("rejected")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_runtime_auth_failure_starts_reauth(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.async_get_data.side_effect = VantivaAuthError("password changed")
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert hass.states.get("sensor.nh20t_wan_ipv4_address").state == STATE_UNAVAILABLE


async def test_runtime_connection_error_then_recovery(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    entity_id = "sensor.nh20t_wan_ipv4_address"
    mock_client.async_get_data.side_effect = VantivaConnectionError("timeout")
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_client.async_get_data.side_effect = None
    mock_client.async_get_data.return_value = make_data()
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "203.0.113.58"
