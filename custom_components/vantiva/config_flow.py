"""Config flow for the Vantiva integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    GatewayInfo,
    VantivaAuthError,
    VantivaClient,
    VantivaConnectionError,
    VantivaError,
    VantivaLockedOutError,
)
from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    LOGGER,
    MAX_CONSIDER_HOME,
    MAX_SCAN_INTERVAL,
    MIN_CONSIDER_HOME,
    MIN_SCAN_INTERVAL,
)
from .coordinator import VantivaConfigEntry

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
            vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
        }
    )


class VantivaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vantiva."""

    VERSION = 1

    async def _async_validate(
        self, host: str, username: str, password: str
    ) -> tuple[GatewayInfo | None, dict[str, str], dict[str, str]]:
        """Log in to the gateway; return (info, errors, description placeholders)."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        session = async_create_clientsession(
            self.hass, auto_cleanup=False, cookie_jar=CookieJar(unsafe=True)
        )
        client = VantivaClient(host, username, password, session)
        info: GatewayInfo | None = None
        try:
            info = await client.async_test_connection()
        except VantivaLockedOutError as err:
            errors["base"] = "locked_out"
            placeholders["wait"] = str(err.wait_seconds) if err.wait_seconds else "?"
        except VantivaAuthError:
            errors["base"] = "invalid_auth"
        except VantivaConnectionError:
            errors["base"] = "cannot_connect"
        except VantivaError:
            LOGGER.exception("Unexpected response from %s", host)
            errors["base"] = "unknown"
        except Exception:
            LOGGER.exception("Unexpected error validating %s", host)
            errors["base"] = "unknown"
        finally:
            # Free the router's single session slot for the integration's own client.
            if client.is_authenticated:
                await client.async_logout()
            # The connector is shared by Home Assistant; detach instead of closing it.
            session.detach()
        return info, errors, placeholders

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"wait": "?"}
        if user_input is not None:
            info, errors, extra = await self._async_validate(
                user_input[CONF_HOST], user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            placeholders.update(extra)
            if info is not None:
                unique_id = info.mac or info.serial or user_input[CONF_HOST]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(
                    title=info.product or "Vantiva gateway", data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(
                {k: v for k, v in (user_input or {}).items() if k != CONF_PASSWORD}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the router rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"wait": "?", "host": entry.data[CONF_HOST]}
        if user_input is not None:
            info, errors, extra = await self._async_validate(
                entry.data[CONF_HOST], entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            placeholders.update(extra)
            if info is not None:
                await self.async_set_unique_id(info.mac or info.serial or entry.data[CONF_HOST])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: VantivaConfigEntry) -> VantivaOptionsFlow:
        """Return the options flow handler."""
        return VantivaOptionsFlow()


class VantivaOptionsFlow(OptionsFlow):
    """Polling and presence options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_CONSIDER_HOME: int(user_input[CONF_CONSIDER_HOME]),
                }
            )
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_CONSIDER_HOME,
                    default=options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_CONSIDER_HOME,
                        max=MAX_CONSIDER_HOME,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
