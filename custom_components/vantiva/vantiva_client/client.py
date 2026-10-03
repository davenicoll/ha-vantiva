"""Async client for Vantiva/Technicolor Homeware gateways."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .exceptions import (
    VantivaAuthError,
    VantivaConnectionError,
    VantivaError,
    VantivaLockedOutError,
    VantivaParseError,
)
from .models import GatewayInfo, GponStats, LanClient, VantivaData, WanStatus
from .parsers import (
    is_login_page,
    parse_csrf_token,
    parse_device_modal,
    parse_gateway_info,
    parse_gpon_stats,
    parse_lan_clients_table,
    parse_wan_status,
)
from .srp import SrpClient

_LOGGER = logging.getLogger(__name__)

PAGE_SYSTEM_INFO = "/modals/system-info-modal.lp"
PAGE_INTERNET = "/modals/internet-modal.lp"
PAGE_GPON = "/modals/gpon-overview-modal.lp"
PAGE_DIAGNOSTICS = "/modals/diagnostics-connection-modal.lp"
PAGE_DEVICES = "/modals/device-modal.lp"
PAGE_DEVICES_TABLE = "/modals/ipv6devices-modal.lp"
PATH_AUTHENTICATE = "/authenticate"
PATH_LAST_ACCESS = "/login.lp?action=lastaccess"

# Never requested: on Homeware 20 this page makes the server drop the connection.
FORBIDDEN_PATHS = frozenset({"/modals/broadband-modal.lp"})


def normalise_host(host: str) -> str:
    """Return ``scheme://host[:port]`` for any accepted host spelling.

    Accepts ``"host"``, ``"host:port"``, ``"http://host"``, ``"https://host/"`` (paths, query
    strings and fragments are dropped). Raises VantivaConnectionError for unusable input.
    """
    value = host.strip()
    if not value:
        raise VantivaConnectionError("No host given")
    if "://" not in value:
        # Bare IPv6 literal without brackets.
        if value.count(":") >= 2 and not value.startswith("["):
            value = f"[{value}]"
        value = f"http://{value}"
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as err:
        raise VantivaConnectionError(f"Invalid host: {host!r}") from err
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise VantivaConnectionError(f"Invalid host: {host!r}")
    hostname = parts.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = hostname if port is None else f"{hostname}:{port}"
    return f"{scheme}://{netloc}"


def _to_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _raise_for_auth_error(payload: dict[str, Any]) -> None:
    """Raise the right exception for an ``{"error": ...}`` login response."""
    error = payload.get("error")
    details: dict[str, Any] = dict(payload)
    if isinstance(error, dict):
        details.update(error)
    wait_seconds = _to_optional_int(details.get("waitTime"))
    wrong_count = _to_optional_int(details.get("wrongCount"))
    if wait_seconds is not None and wait_seconds > 0:
        raise VantivaLockedOutError(wait_seconds=wait_seconds, wrong_count=wrong_count)
    message = "Router rejected the credentials"
    if wrong_count is not None:
        message += f" (failed attempts: {wrong_count})"
    raise VantivaAuthError(message)


class _StaleCsrfError(Exception):
    """Internal: the router answered a login step with HTTP 403."""


class VantivaClient:
    """Async client for one Homeware gateway.

    The router allows a single authenticated session; the client logs in lazily, keeps the
    session for as long as the router accepts it, and logs in again once when a page comes
    back as the login form (or 401/403).
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        *,
        request_timeout: float = 15.0,
        verify_ssl: bool = True,
    ) -> None:
        """Create a client; ``session`` is owned (and closed) by the caller."""
        self._base_url = normalise_host(host)
        self._host_for_logs = urlsplit(self._base_url).netloc
        self._username = username
        self._password = password
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._ssl: bool = verify_ssl
        self._cookies: dict[str, str] = {}
        self._csrf_token: str | None = None
        self._authenticated = False
        self._login_generation = 0
        self._login_lock = asyncio.Lock()

    def __repr__(self) -> str:
        """Return a representation without credentials."""
        return f"VantivaClient(base_url={self._base_url!r})"

    @property
    def base_url(self) -> str:
        """Return the normalised base URL, e.g. ``http://192.168.1.254``."""
        return self._base_url

    @property
    def is_authenticated(self) -> bool:
        """Return True while the client holds a session the router accepted."""
        return self._authenticated

    # ----------------------------------------------------------------------------------------
    # Transport
    # ----------------------------------------------------------------------------------------

    async def _async_request(
        self, method: str, path: str, data: dict[str, str] | None = None
    ) -> tuple[int, str]:
        """Perform one request; return ``(status, body)``. Never logs bodies or cookies."""
        if path.split("?", 1)[0] in FORBIDDEN_PATHS:
            raise VantivaError(f"Refusing to request {path}")
        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {}
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        if data is not None:
            headers["X-Requested-With"] = "XMLHttpRequest"
        try:
            async with self._session.request(
                method,
                url,
                data=data,
                headers=headers,
                timeout=self._timeout,
                ssl=self._ssl,
                allow_redirects=True,
            ) as response:
                self._store_cookies(response)
                body = await response.text(errors="replace")
                status = response.status
        except (TimeoutError, aiohttp.ClientError) as err:
            raise VantivaConnectionError(
                f"Error talking to {self._host_for_logs}: {type(err).__name__}"
            ) from err
        if status >= 500:
            raise VantivaConnectionError(
                f"{self._host_for_logs} returned HTTP {status} for {path.split('?', 1)[0]}"
            )
        return status, body

    def _store_cookies(self, response: aiohttp.ClientResponse) -> None:
        jars: list[SimpleCookie] = [r.cookies for r in response.history]
        jars.append(response.cookies)
        for jar in jars:
            for name, morsel in jar.items():
                if morsel.value:
                    self._cookies[name] = morsel.value
                else:
                    self._cookies.pop(name, None)

    # ----------------------------------------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------------------------------------

    async def async_login(self) -> None:
        """Run the full SRP-6a login (see docs/ARCHITECTURE.md)."""
        async with self._login_lock:
            await self._async_login_locked()

    async def _async_login_locked(self) -> None:
        self._authenticated = False
        self._csrf_token = None
        self._cookies.clear()
        _LOGGER.debug("Logging in to %s", self._host_for_logs)
        try:
            await self._async_srp_exchange()
        except _StaleCsrfError:
            _LOGGER.debug("Stale CSRF token on %s; retrying login once", self._host_for_logs)
            try:
                await self._async_srp_exchange()
            except _StaleCsrfError as err:
                raise VantivaConnectionError(
                    f"{self._host_for_logs} rejected the login request twice (HTTP 403)"
                ) from err

        # What the GUI does after a successful login; harmless.
        await self._async_request("GET", PATH_LAST_ACCESS)
        status, body = await self._async_request("GET", "/")
        if status in (401, 403) or is_login_page(body):
            raise VantivaAuthError("Login was accepted but the router did not keep the session")
        self._csrf_token = parse_csrf_token(body) or self._csrf_token
        self._authenticated = True
        self._login_generation += 1
        _LOGGER.debug("Logged in to %s", self._host_for_logs)

    async def _async_fetch_login_token(self) -> str:
        status, body = await self._async_request("GET", "/")
        token = parse_csrf_token(body)
        if token is None:
            raise VantivaParseError(
                f"No CSRF token on the login page of {self._host_for_logs} (HTTP {status})"
            )
        return token

    async def _async_post_auth(self, form: dict[str, str]) -> dict[str, Any]:
        status, body = await self._async_request("POST", PATH_AUTHENTICATE, form)
        if status == 403:
            raise _StaleCsrfError
        try:
            payload = json.loads(body)
        except ValueError as err:
            raise VantivaAuthError(f"Unexpected non-JSON login response (HTTP {status})") from err
        if not isinstance(payload, dict):
            raise VantivaAuthError(f"Unexpected login response (HTTP {status})")
        if "error" in payload:
            _raise_for_auth_error(payload)
        if status >= 400:
            raise VantivaAuthError(f"Login request failed (HTTP {status})")
        return payload

    async def _async_srp_exchange(self) -> None:
        token = await self._async_fetch_login_token()
        srp = SrpClient(self._username, self._password)
        a_hex = srp.start()
        challenge = await self._async_post_auth(
            {"CSRFtoken": token, "I": self._username, "A": a_hex}
        )
        salt = challenge.get("s")
        b_hex = challenge.get("B")
        if not isinstance(salt, str) or not isinstance(b_hex, str):
            raise VantivaAuthError("Router did not send an SRP challenge")
        m_hex = srp.process_challenge(salt, b_hex)
        proof = await self._async_post_auth({"CSRFtoken": token, "M": m_hex})
        server_proof = proof.get("M")
        if not isinstance(server_proof, str) or not srp.verify(server_proof):
            raise VantivaAuthError("Router proof did not verify")
        self._csrf_token = token

    async def async_logout(self) -> None:
        """Log out (``POST / do_signout=1``); errors are swallowed, local state always cleared."""
        try:
            if self._authenticated and self._csrf_token:
                await self._async_request(
                    "POST", "/", {"do_signout": "1", "CSRFtoken": self._csrf_token}
                )
                _LOGGER.debug("Logged out of %s", self._host_for_logs)
        except VantivaError as err:
            _LOGGER.debug("Ignoring logout error for %s: %s", self._host_for_logs, err)
        finally:
            self._authenticated = False
            self._csrf_token = None
            self._cookies.clear()

    async def _async_ensure_login(self) -> None:
        if self._authenticated:
            return
        async with self._login_lock:
            if not self._authenticated:
                await self._async_login_locked()

    async def _async_relogin(self, seen_generation: int) -> None:
        """Log in again unless another task already did since ``seen_generation``."""
        async with self._login_lock:
            if self._login_generation != seen_generation and self._authenticated:
                return
            await self._async_login_locked()

    # ----------------------------------------------------------------------------------------
    # Pages
    # ----------------------------------------------------------------------------------------

    async def _async_fetch_page(self, path: str, *, allow_missing: bool = False) -> str | None:
        """GET a page as the logged-in user, logging in again once if the session was lost.

        Returns None for a missing page (HTTP 404, or a page that stays on the login form after
        a fresh login, i.e. role-restricted) when ``allow_missing`` is set; otherwise raises
        VantivaParseError in those cases.
        """
        await self._async_ensure_login()
        generation = self._login_generation
        _LOGGER.debug("Fetching %s from %s", path, self._host_for_logs)
        status, body = await self._async_request("GET", path)
        if status in (401, 403) or is_login_page(body):
            _LOGGER.debug("Session lost on %s while fetching %s", self._host_for_logs, path)
            await self._async_relogin(generation)
            status, body = await self._async_request("GET", path)
            if status in (401, 403) or is_login_page(body):
                if allow_missing:
                    return None
                raise VantivaParseError(f"{path} is not accessible after logging in")
        if status == 404:
            if allow_missing:
                return None
            raise VantivaParseError(f"{path} does not exist on this gateway")
        if status >= 400:
            raise VantivaConnectionError(f"HTTP {status} fetching {path}")
        return body

    async def _async_fetch_required(self, path: str) -> str:
        body = await self._async_fetch_page(path)
        if body is None:  # pragma: no cover - only with allow_missing
            raise VantivaParseError(f"{path} returned no content")
        return body

    async def async_get_gateway_info(self) -> GatewayInfo:
        """Return gateway identity and health from the system information page."""
        return parse_gateway_info(await self._async_fetch_required(PAGE_SYSTEM_INFO))

    async def async_get_wan_status(self) -> WanStatus:
        """Return WAN state from the internet and connection diagnostics pages."""
        await self._async_ensure_login()
        internet, diagnostics = await asyncio.gather(
            self._async_fetch_required(PAGE_INTERNET),
            self._async_fetch_page(PAGE_DIAGNOSTICS, allow_missing=True),
        )
        return parse_wan_status(internet, diagnostics)

    async def async_get_gpon_stats(self) -> GponStats | None:
        """Return GPON optics, or None if the gateway has no GPON overview page."""
        body = await self._async_fetch_page(PAGE_GPON, allow_missing=True)
        return parse_gpon_stats(body) if body is not None else None

    async def async_get_clients(self) -> dict[str, LanClient]:
        """Return LAN clients keyed by MAC.

        Uses the JSON arrays in ``device-modal.lp``; falls back to the table in
        ``ipv6devices-modal.lp`` when those arrays are missing or empty.
        """
        body = await self._async_fetch_page(PAGE_DEVICES, allow_missing=True)
        clients = parse_device_modal(body) if body is not None else None
        if clients:
            return clients
        _LOGGER.debug("No device arrays on %s; using the client table", self._host_for_logs)
        table = await self._async_fetch_page(PAGE_DEVICES_TABLE, allow_missing=True)
        if table is None:
            if clients is not None:
                return clients
            raise VantivaParseError("No client list available on this gateway")
        return parse_lan_clients_table(table)

    async def async_get_data(self) -> VantivaData:
        """Fetch a full snapshot; pages are requested concurrently after one login."""
        await self._async_ensure_login()
        gateway, wan, gpon, clients = await asyncio.gather(
            self.async_get_gateway_info(),
            self.async_get_wan_status(),
            self.async_get_gpon_stats(),
            self.async_get_clients(),
        )
        return VantivaData(
            gateway=gateway,
            wan=wan,
            gpon=gpon,
            clients=clients,
            fetched_at=datetime.now(UTC),
        )

    async def async_test_connection(self) -> GatewayInfo:
        """Log in and read the gateway information (used by the config flow)."""
        await self.async_login()
        return await self.async_get_gateway_info()
