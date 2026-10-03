"""Client tests: login flow, session handling and data fetching (aioresponses)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, timedelta
from typing import Any

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from custom_components.vantiva.vantiva_client import (
    ConnectionType,
    VantivaAuthError,
    VantivaClient,
    VantivaConnectionError,
    VantivaError,
    VantivaLockedOutError,
    VantivaParseError,
)
from custom_components.vantiva.vantiva_client.client import normalise_host
from tests.client.fake_router import FakeRouter, fixture, nh20t_pages

BASE = "http://192.168.1.254"
PASSWORD = "correct horse"


@pytest.fixture
def mocked() -> Iterator[aioresponses]:
    with aioresponses() as m:
        yield m


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def router(mocked: aioresponses) -> FakeRouter:
    fake = FakeRouter(base=BASE, password=PASSWORD, pages=nh20t_pages())
    fake.install(mocked)
    return fake


def make_client(
    session: aiohttp.ClientSession, password: str = PASSWORD, host: str = "192.168.1.254"
) -> VantivaClient:
    return VantivaClient(host, "admin", password, session)


# --------------------------------------------------------------------------------------------
# Host normalisation
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("192.168.1.254", "http://192.168.1.254"),
        (" 192.168.1.254 ", "http://192.168.1.254"),
        ("192.168.1.254:8080", "http://192.168.1.254:8080"),
        ("http://192.168.1.254", "http://192.168.1.254"),
        ("http://192.168.1.254/", "http://192.168.1.254"),
        ("https://192.168.1.254/", "https://192.168.1.254"),
        ("HTTPS://router.lan:8443/login.lp?x=1#y", "https://router.lan:8443"),
        ("router.lan", "http://router.lan"),
        ("fe80::1", "http://[fe80::1]"),
        ("[fe80::1]:8080", "http://[fe80::1]:8080"),
        ("http://[2001:db8::1]/", "http://[2001:db8::1]"),
    ],
)
def test_normalise_host(host: str, expected: str) -> None:
    assert normalise_host(host) == expected


@pytest.mark.parametrize(
    "host", ["", "   ", "ftp://router", "http://", "host:notaport", "http://:80"]
)
def test_normalise_host_invalid(host: str) -> None:
    with pytest.raises(VantivaConnectionError):
        normalise_host(host)


async def test_base_url_and_repr(session: aiohttp.ClientSession) -> None:
    client = VantivaClient("https://192.168.1.254/", "admin", "hunter2", session)
    assert client.base_url == "https://192.168.1.254"
    assert "hunter2" not in repr(client)
    assert client.is_authenticated is False


# --------------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------------


async def test_login_success(
    router: FakeRouter, session: aiohttp.ClientSession, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client(session)
    await client.async_login()
    assert client.is_authenticated
    assert router.logins == 1
    assert ("GET", "/login.lp?action=lastaccess") in router.calls
    posts = [c for c in router.calls if c[0] == "POST"]
    assert posts == [("POST", "/authenticate"), ("POST", "/authenticate")]
    # No secrets in the logs.
    assert PASSWORD not in caplog.text
    assert "sessionID" not in caplog.text
    assert "s1" not in caplog.text.split()
    assert router.server is not None
    assert router.server.salt_hex not in caplog.text
    assert "192.168.1.254" in caplog.text


async def test_login_bad_password(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    client = make_client(session, password="wrong")
    with pytest.raises(VantivaAuthError) as err:
        await client.async_login()
    assert not isinstance(err.value, VantivaLockedOutError)
    assert not client.is_authenticated
    # Exactly one attempt: never retried after an auth error.
    assert [c for c in router.calls if c[0] == "POST"] == [("POST", "/authenticate")] * 2


async def test_login_bad_password_with_wrong_count(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    router.auth_error = {"error": {"waitTime": 0, "wrongCount": 2}}
    with pytest.raises(VantivaAuthError, match="failed attempts: 2") as err:
        await make_client(session, password="wrong").async_login()
    assert not isinstance(err.value, VantivaLockedOutError)


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"waitTime": 30, "wrongCount": 5}},
        {"error": "failed", "waitTime": "30", "wrongCount": "5"},
        {"error": {"waitTime": 30.0, "wrongCount": 5}},
    ],
)
async def test_login_locked_out(
    router: FakeRouter, session: aiohttp.ClientSession, payload: dict[str, Any]
) -> None:
    router.auth_error = payload
    with pytest.raises(VantivaLockedOutError) as err:
        await make_client(session, password="wrong").async_login()
    assert err.value.wait_seconds == 30
    assert err.value.wrong_count == 5
    assert "30" in str(err.value)
    assert isinstance(err.value, VantivaAuthError)


async def test_login_locked_out_at_identify_step(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    router.auth_error = {"error": {"waitTime": 12, "wrongCount": True}}
    client = VantivaClient(BASE, "nobody", PASSWORD, session)
    with pytest.raises(VantivaLockedOutError) as err:
        await client.async_login()
    assert err.value.wait_seconds == 12
    assert err.value.wrong_count is None
    assert [c for c in router.calls if c[0] == "POST"] == [("POST", "/authenticate")]


async def test_login_403_then_retry(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    router.forbid_auth_posts = 1
    client = make_client(session)
    await client.async_login()
    assert client.is_authenticated
    assert router.logins == 1
    # Fresh token fetched: two GETs of "/" before the successful exchange.
    assert [c for c in router.calls if c[0] == "POST"] == [("POST", "/authenticate")] * 3


async def test_login_403_on_proof_step_then_retry(
    mocked: aioresponses, session: aiohttp.ClientSession
) -> None:
    router = FakeRouter(base=BASE, password=PASSWORD, pages=nh20t_pages())
    original_post = router._post
    state = {"count": 0}

    def post(url: Any, **kwargs: Any) -> CallbackResult:
        if "M" in (kwargs.get("data") or {}) and state["count"] == 0:
            state["count"] += 1
            return CallbackResult(status=403, body="")
        return original_post(url, **kwargs)

    router._post = post  # type: ignore[method-assign]
    router.install(mocked)
    client = make_client(session)
    await client.async_login()
    assert client.is_authenticated


async def test_login_403_twice_gives_up(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    router.forbid_auth_posts = 5
    with pytest.raises(VantivaConnectionError):
        await make_client(session).async_login()
    assert len([c for c in router.calls if c[0] == "POST"]) == 2


async def test_login_connection_error(mocked: aioresponses, session: aiohttp.ClientSession) -> None:
    mocked.get(f"{BASE}/", exception=aiohttp.ClientConnectionError("refused"))
    with pytest.raises(VantivaConnectionError):
        await make_client(session).async_login()


async def test_login_timeout(mocked: aioresponses, session: aiohttp.ClientSession) -> None:
    mocked.get(f"{BASE}/", exception=TimeoutError())
    with pytest.raises(VantivaConnectionError):
        await make_client(session).async_login()


async def test_login_server_error(mocked: aioresponses, session: aiohttp.ClientSession) -> None:
    mocked.get(f"{BASE}/", status=502, body="Bad gateway")
    with pytest.raises(VantivaConnectionError, match="502"):
        await make_client(session).async_login()


async def test_login_page_without_csrf_token(
    mocked: aioresponses, session: aiohttp.ClientSession
) -> None:
    mocked.get(f"{BASE}/", status=200, body="<html>not a homeware gui</html>")
    with pytest.raises(VantivaParseError):
        await make_client(session).async_login()


def _login_page_then(mocked: aioresponses, *bodies: tuple[int, str]) -> None:
    mocked.get(f"{BASE}/", status=200, body=fixture("login.html"), repeat=True)
    for status, body in bodies:
        mocked.post(f"{BASE}/authenticate", status=status, body=body)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, "<html>oops</html>"),
        (200, "[1, 2]"),
        (200, "{}"),
        (200, '{"s": 1, "B": null}'),
        (400, '{"s": "00", "B": "05"}'),
    ],
)
async def test_login_bad_challenge(
    mocked: aioresponses, session: aiohttp.ClientSession, status: int, body: str
) -> None:
    _login_page_then(mocked, (status, body))
    with pytest.raises(VantivaAuthError):
        await make_client(session).async_login()


@pytest.mark.parametrize("proof", ['{"M": "00"}', "{}", '{"M": 5}'])
async def test_login_bad_server_proof(
    mocked: aioresponses, session: aiohttp.ClientSession, proof: str
) -> None:
    _login_page_then(mocked, (200, '{"s": "AF1A0C75", "B": "05"}'), (200, proof))
    with pytest.raises(VantivaAuthError):
        await make_client(session).async_login()


async def test_login_session_not_kept(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    router.home_page = fixture("login.html")
    with pytest.raises(VantivaAuthError, match="did not keep"):
        await make_client(session).async_login()


# --------------------------------------------------------------------------------------------
# Logout
# --------------------------------------------------------------------------------------------


async def test_logout(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    client = make_client(session)
    await client.async_login()
    await client.async_logout()
    assert router.logouts == 1
    assert not client.is_authenticated
    # Not logged in: logout does nothing on the wire.
    await client.async_logout()
    assert router.logouts == 1


async def test_logout_swallows_errors(mocked: aioresponses, session: aiohttp.ClientSession) -> None:
    router = FakeRouter(base=BASE, password=PASSWORD, pages=nh20t_pages())
    router.install(mocked)
    client = make_client(session)
    await client.async_login()
    mocked._matches.clear()  # type: ignore[attr-defined]
    mocked.post(f"{BASE}/", exception=aiohttp.ClientConnectionError("gone"))
    await client.async_logout()
    assert not client.is_authenticated


# --------------------------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------------------------


async def test_get_data(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    client = make_client(session)
    data = await client.async_get_data()
    assert router.logins == 1
    assert data.gateway.product == "NH20T"
    assert data.wan.connected is True
    assert data.wan.link_up is True
    assert data.gpon is not None
    assert data.gpon.rx_power_dbm == pytest.approx(-17.544872)
    assert len(data.clients) == 36
    assert data.active_client_count == 31
    assert data.fetched_at.tzinfo is UTC
    assert all(c.connection is ConnectionType.WIRED for c in data.clients.values())
    assert not any("broadband" in path for _, path in router.calls)
    assert not any("ipv6devices" in path for _, path in router.calls)
    # Session reused on the next poll.
    await client.async_get_data()
    assert router.logins == 1


async def test_test_connection(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    info = await make_client(session).async_test_connection()
    assert info.mac == "02:00:00:00:00:26"
    assert info.uptime == timedelta(days=49, hours=22, minutes=3, seconds=52)


async def test_relogin_when_login_page_returned(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    client = make_client(session)
    await client.async_get_gateway_info()
    assert router.logins == 1
    router.expire_session()  # e.g. somebody logged in to the web GUI
    data = await client.async_get_data()
    assert data.gateway.product == "NH20T"
    # All concurrent fetches saw the login page but only one re-login happened.
    assert router.logins == 2


@pytest.mark.parametrize("status", [401, 403])
async def test_relogin_on_status(
    router: FakeRouter, session: aiohttp.ClientSession, status: int
) -> None:
    client = make_client(session)
    await client.async_login()
    state = {"done": False}

    def on_get(path: str) -> CallbackResult | None:
        if path == "/modals/system-info-modal.lp" and not state["done"]:
            state["done"] = True
            return CallbackResult(status=status, body="")
        return None

    router.on_get = on_get
    info = await client.async_get_gateway_info()
    assert info.product == "NH20T"
    assert router.logins == 2


async def test_relogin_only_once(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    client = make_client(session)
    router.on_get = lambda path: (
        CallbackResult(status=200, body=fixture("login.html"))
        if path == "/modals/system-info-modal.lp"
        else None
    )
    with pytest.raises(VantivaParseError, match="not accessible"):
        await client.async_get_gateway_info()
    assert router.logins == 2


async def test_relogin_with_bad_password_raises_auth(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    client = make_client(session)
    await client.async_login()
    router.expire_session()
    router.password = "changed"
    with pytest.raises(VantivaAuthError):
        await client.async_get_gateway_info()
    assert not client.is_authenticated


async def test_gpon_missing_returns_none(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    del router.pages["/modals/gpon-overview-modal.lp"]
    del router.pages["/modals/diagnostics-connection-modal.lp"]
    client = make_client(session)
    data = await client.async_get_data()
    assert data.gpon is None
    assert data.wan.link_up is None
    assert data.wan.connected is True


async def test_gpon_role_restricted_returns_none(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    router.pages["/modals/gpon-overview-modal.lp"] = fixture("login.html")
    assert await make_client(session).async_get_gpon_stats() is None


async def test_required_page_missing_raises(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    del router.pages["/modals/system-info-modal.lp"]
    with pytest.raises(VantivaParseError, match="does not exist"):
        await make_client(session).async_get_gateway_info()


async def test_page_http_error(router: FakeRouter, session: aiohttp.ClientSession) -> None:
    router.pages["/modals/system-info-modal.lp"] = 418
    with pytest.raises(VantivaConnectionError, match="418"):
        await make_client(session).async_get_gateway_info()
    router.pages["/modals/system-info-modal.lp"] = 503
    with pytest.raises(VantivaConnectionError, match="503"):
        await make_client(session).async_get_gateway_info()


async def test_clients_fallback_to_table(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    router.pages["/modals/device-modal.lp"] = "<html>no arrays here</html>"
    clients = await make_client(session).async_get_clients()
    assert len(clients) == 37
    assert ("GET", "/modals/ipv6devices-modal.lp") in router.calls


async def test_clients_empty_arrays_and_no_table(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    router.pages["/modals/device-modal.lp"] = "<script>var ethernet_data = [];</script>"
    del router.pages["/modals/ipv6devices-modal.lp"]
    assert await make_client(session).async_get_clients() == {}


async def test_clients_nothing_available(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    del router.pages["/modals/device-modal.lp"]
    del router.pages["/modals/ipv6devices-modal.lp"]
    with pytest.raises(VantivaParseError):
        await make_client(session).async_get_clients()


async def test_connection_error_during_fetch(
    mocked: aioresponses, session: aiohttp.ClientSession
) -> None:
    router = FakeRouter(base=BASE, password=PASSWORD, pages=nh20t_pages())

    def on_get(path: str) -> CallbackResult | None:
        if path.startswith("/modals/"):
            raise aiohttp.ServerDisconnectedError()
        return None

    router.on_get = on_get
    router.install(mocked)
    with pytest.raises(VantivaConnectionError):
        await make_client(session).async_get_data()


async def test_forbidden_page_never_requested(session: aiohttp.ClientSession) -> None:
    client = make_client(session)
    with pytest.raises(VantivaError, match="Refusing"):
        await client._async_request("GET", "/modals/broadband-modal.lp?x=1")


async def test_cookie_cleared_when_router_expires_it(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    client = make_client(session)
    await client.async_login()
    assert client._cookies == {"sessionID": "s1"}
    router.on_get = lambda path: (
        CallbackResult(status=200, body="", headers={"Set-Cookie": 'sessionID=""; Path=/'})
        if path == "/expire"
        else None
    )
    await client._async_request("GET", "/expire")
    assert client._cookies == {}


async def test_concurrent_first_login_happens_once(
    router: FakeRouter, session: aiohttp.ClientSession
) -> None:
    client = make_client(session)
    await asyncio.gather(
        client.async_get_gateway_info(),
        client.async_get_gpon_stats(),
        client.async_get_wan_status(),
    )
    assert router.logins == 1
