"""Fixtures for the Vantiva integration tests."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Client stand-in -------------------------------------------------------------------------
# The real client lives in custom_components/vantiva/vantiva_client and is developed on another
# branch. If it is not present, install tests/integration/fake_client.py under its module name
# before anything imports the integration. With the real package present this is a no-op.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLIENT_PKG = "custom_components.vantiva.vantiva_client"
if not (_REPO_ROOT / "custom_components" / "vantiva" / "vantiva_client" / "__init__.py").exists():
    _spec = importlib.util.spec_from_file_location(
        _CLIENT_PKG, Path(__file__).with_name("fake_client.py")
    )
    assert _spec is not None and _spec.loader is not None
    _fake = importlib.util.module_from_spec(_spec)
    sys.modules[_CLIENT_PKG] = _fake
    _spec.loader.exec_module(_fake)
    USING_FAKE_CLIENT = True
else:
    USING_FAKE_CLIENT = False

from custom_components.vantiva.const import DOMAIN  # noqa: E402
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from pytest_homeassistant_custom_component.syrupy import (  # noqa: E402
    HomeAssistantSnapshotExtension,
)
from syrupy.assertion import SnapshotAssertion  # noqa: E402

from .factories import GATEWAY_MAC, make_data, make_gateway  # noqa: E402

HOST = "192.168.1.254"
PASSWORD = "test-password"
ENTRY_DATA = {CONF_HOST: HOST, CONF_USERNAME: "admin", CONF_PASSWORD: PASSWORD}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in every test."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Pin the Home Assistant snapshot extension (plugin load order is not deterministic)."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch the client class in both modules that instantiate it."""
    client = MagicMock()
    client.base_url = f"http://{HOST}"
    client.is_authenticated = True
    client.async_login = AsyncMock()
    client.async_logout = AsyncMock()
    client.async_test_connection = AsyncMock(return_value=make_gateway())
    client.async_get_data = AsyncMock(return_value=make_data())
    with (
        patch("custom_components.vantiva.VantivaClient", return_value=client) as cls,
        patch("custom_components.vantiva.config_flow.VantivaClient", new=cls),
    ):
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the default gateway."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="NH20T",
        unique_id=GATEWAY_MAC,
        data=dict(ENTRY_DATA),
        entry_id="01J0000000000000000000TEST",
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration with the mocked client."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
