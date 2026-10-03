"""The Vantiva gateway integration."""

from __future__ import annotations

from aiohttp import CookieJar
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import VantivaClient
from .const import PLATFORMS
from .coordinator import VantivaConfigEntry, VantivaCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: VantivaConfigEntry) -> bool:
    """Set up Vantiva from a config entry."""
    # The router authenticates with a sessionID cookie set by a bare IP host, which the default
    # aiohttp cookie jar refuses. A dedicated session also keeps this cookie away from other
    # integrations; it is closed automatically when the entry unloads.
    session = async_create_clientsession(hass, cookie_jar=CookieJar(unsafe=True))
    client = VantivaClient(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session,
    )
    coordinator = VantivaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VantivaConfigEntry) -> bool:
    """Unload a config entry and free the router's single session slot."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_logout()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: VantivaConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
