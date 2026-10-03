"""Config, reauth and options flow tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from custom_components.vantiva.api import (
    VantivaAuthError,
    VantivaConnectionError,
    VantivaLockedOutError,
    VantivaParseError,
)
from custom_components.vantiva.const import CONF_CONSIDER_HOME, CONF_SCAN_INTERVAL, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import ENTRY_DATA, HOST
from .factories import GATEWAY_MAC, make_gateway


async def test_user_flow_success(hass: HomeAssistant, mock_client: MagicMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NH20T"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == GATEWAY_MAC
    mock_client.async_test_connection.assert_awaited_once()
    mock_client.async_logout.assert_awaited()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (VantivaAuthError("bad password"), "invalid_auth"),
        (VantivaConnectionError("timeout"), "cannot_connect"),
        (VantivaLockedOutError(wait_seconds=60, wrong_count=3), "locked_out"),
        (VantivaParseError("odd page"), "unknown"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recover(
    hass: HomeAssistant, mock_client: MagicMock, side_effect: Exception, error: str
) -> None:
    mock_client.async_test_connection.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.async_test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_locked_out_shows_wait(hass: HomeAssistant, mock_client: MagicMock) -> None:
    mock_client.async_test_connection.side_effect = VantivaLockedOutError(
        wait_seconds=120, wrong_count=5
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    assert result["errors"] == {"base": "locked_out"}
    assert result["description_placeholders"]["wait"] == "120"


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_HOST: "192.168.1.1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # The host of the existing entry follows the gateway to its new address.
    assert mock_config_entry.data[CONF_HOST] == "192.168.1.1"


async def test_reauth_flow(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_client.async_test_connection.side_effect = VantivaAuthError("still wrong")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.async_test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
    assert mock_config_entry.data[CONF_USERNAME] == "admin"
    assert mock_config_entry.data[CONF_HOST] == HOST


async def test_reauth_wrong_device(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_client.async_test_connection.return_value = make_gateway(mac="02:00:00:00:00:99")
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_PASSWORD] != "new-password"


async def test_options_flow(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    entry = init_integration
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_CONSIDER_HOME: 300}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 60, CONF_CONSIDER_HOME: 300}
    # The entry reloads and the coordinator picks up the new values.
    coordinator = entry.runtime_data
    assert coordinator.update_interval.total_seconds() == 60
    assert coordinator.consider_home.total_seconds() == 300
