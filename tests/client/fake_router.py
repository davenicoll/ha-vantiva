"""Test doubles: an independent SRP-6a server and a fake Homeware router for aioresponses."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aioresponses import CallbackResult, aioresponses
from yarl import URL

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "nh20t"

# RFC 5054 2048-bit group, written out independently of the library.
N = int(
    "AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050A37329CBB4A099ED8193E075"
    "7767A13DD52312AB4B03310DCD7F48A9DA04FD50E8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE8"
    "2918A9962F0B93B855F97993EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B14773BCA97B43A"
    "23FB801676BD207A436C6481F1D2B9078717461A5B9D32E688F87748544523B524B0D57D5EA77A2775D2ECFA"
    "032CFBDBF52FB3786160279004E57AE6AF874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8"
    "E9DBFBB694B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73",
    16,
)
G = 2


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def int_bytes(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")


def pad(value: int) -> bytes:
    return value.to_bytes(256, "big")


def k_value() -> int:
    return int.from_bytes(sha(int_bytes(N) + pad(G)), "big")


class SrpServer:
    """Server side of the Homeware SRP variant, derived from first principles."""

    def __init__(self, username: str, password: str, salt: bytes, b: int | None = None) -> None:
        self.username = username
        self.salt = salt
        self.odd_b_hex = False
        inner = sha(f"{username}:{password}".encode())
        self.x = int.from_bytes(sha(salt + inner), "big")
        self.v = pow(G, self.x, N)
        self.b = b if b is not None else secrets.randbits(256)
        self.B = (k_value() * self.v + pow(G, self.b, N)) % N
        self.expected_m1: bytes | None = None
        self.m2: bytes | None = None

    @property
    def salt_hex(self) -> str:
        return self.salt.hex().upper()

    @property
    def b_hex(self) -> str:
        hex_value = format(self.B, "X")
        return hex_value if self.odd_b_hex or len(hex_value) % 2 == 0 else "0" + hex_value

    def challenge(self, a_hex: str) -> None:
        a_int = int(a_hex, 16)
        a_bytes = bytes.fromhex(a_hex)
        u = int.from_bytes(sha(pad(a_int) + pad(self.B)), "big")
        s = pow(a_int * pow(self.v, u, N), self.b, N)
        key = sha(int_bytes(s))
        h_n = sha(int_bytes(N))
        h_g = sha(int_bytes(G))
        h_xor = bytes(i ^ j for i, j in zip(h_n, h_g, strict=True))
        b_bytes = bytes.fromhex(self.b_hex if len(self.b_hex) % 2 == 0 else "0" + self.b_hex)
        self.expected_m1 = sha(
            h_xor + sha(self.username.encode()) + self.salt + a_bytes + b_bytes + key
        )
        self.m2 = sha(a_bytes + self.expected_m1 + key)


@dataclass
class FakeRouter:
    """Callback-driven fake of the router's HTTP interface."""

    base: str = "http://192.168.1.254"
    username: str = "admin"
    password: str = "correct horse"
    auth_error: dict[str, Any] = field(default_factory=lambda: {"error": "failed"})
    pages: dict[str, str | int] = field(default_factory=dict)
    forbid_auth_posts: int = 0
    session_counter: int = 0
    valid_session: str | None = None
    logins: int = 0
    logouts: int = 0
    calls: list[tuple[str, str]] = field(default_factory=list)
    server: SrpServer | None = None
    login_page: str = field(default_factory=lambda: fixture("login.html"))
    home_page: str = field(default_factory=lambda: fixture("home.html"))
    on_get: Callable[[str], CallbackResult | None] | None = None

    def install(self, mocked: aioresponses) -> None:
        pattern = re.compile(rf"^{re.escape(self.base)}/.*$")
        mocked.get(pattern, callback=self._get, repeat=True)
        mocked.post(pattern, callback=self._post, repeat=True)

    def _cookie(self, kwargs: dict[str, Any]) -> str | None:
        header = (kwargs.get("headers") or {}).get("Cookie", "")
        match = re.search(r"sessionID=([^;]+)", header)
        return match.group(1) if match else None

    def _new_session_headers(self) -> dict[str, str]:
        self.session_counter += 1
        return {"Set-Cookie": f"sessionID=s{self.session_counter}; Path=/; HttpOnly"}

    def expire_session(self) -> None:
        self.valid_session = None

    def _get(self, url: URL, **kwargs: Any) -> CallbackResult:
        path = url.path_qs
        self.calls.append(("GET", path))
        assert "broadband-modal" not in path
        if self.on_get is not None:
            override = self.on_get(path)
            if override is not None:
                return override
        cookie = self._cookie(kwargs)
        logged_in = cookie is not None and cookie == self.valid_session
        headers = {} if cookie else self._new_session_headers()
        if url.path == "/":
            body = self.home_page if logged_in else self.login_page
            return CallbackResult(status=200, body=body, headers=headers)
        if url.path == "/login.lp":
            return CallbackResult(status=200, body="", headers=headers)
        if not logged_in:
            return CallbackResult(status=200, body=self.login_page, headers=headers)
        page = self.pages.get(url.path)
        if page is None:
            return CallbackResult(status=404, body="Not Found")
        if isinstance(page, int):
            return CallbackResult(status=page, body="")
        return CallbackResult(status=200, body=page)

    def _post(self, url: URL, **kwargs: Any) -> CallbackResult:
        self.calls.append(("POST", url.path))
        data: dict[str, str] = kwargs.get("data") or {}
        cookie = self._cookie(kwargs)
        if url.path == "/" and data.get("do_signout") == "1":
            self.logouts += 1
            self.valid_session = None
            return CallbackResult(status=200, body=self.login_page)
        assert url.path == "/authenticate"
        assert data.get("CSRFtoken")
        if self.forbid_auth_posts > 0:
            self.forbid_auth_posts -= 1
            return CallbackResult(status=403, body="Forbidden")
        if "A" in data:
            if data.get("I") != self.username:
                return CallbackResult(status=200, body=json.dumps(self.auth_error))
            self.server = SrpServer(self.username, self.password, secrets.token_bytes(4))
            self.server.challenge(data["A"])
            body = json.dumps({"s": self.server.salt_hex, "B": self.server.b_hex})
            return CallbackResult(status=200, body=body, content_type="application/json")
        assert self.server is not None and self.server.expected_m1 is not None
        if bytes.fromhex(data["M"]) != self.server.expected_m1:
            return CallbackResult(status=200, body=json.dumps(self.auth_error))
        assert self.server.m2 is not None
        self.logins += 1
        self.valid_session = cookie
        return CallbackResult(status=200, body=json.dumps({"M": self.server.m2.hex().upper()}))


def nh20t_pages() -> dict[str, str | int]:
    return {
        "/modals/system-info-modal.lp": fixture("system-info-modal.html"),
        "/modals/internet-modal.lp": fixture("internet-modal.html"),
        "/modals/gpon-overview-modal.lp": fixture("gpon-overview-modal.html"),
        "/modals/diagnostics-connection-modal.lp": fixture("diagnostics-connection-modal.html"),
        "/modals/device-modal.lp": fixture("device-modal.html"),
        "/modals/ipv6devices-modal.lp": fixture("ipv6devices-modal.html"),
    }
