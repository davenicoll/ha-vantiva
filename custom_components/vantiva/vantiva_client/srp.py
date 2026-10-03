"""SRP-6a client mirroring the Homeware ``/js/srp-min.js`` implementation.

The router's JavaScript uses the RFC 5054 2048-bit group with ``g = 2`` and SHA-256. Most
intermediate values are concatenated as hex strings and then hashed as the bytes those hex
strings encode, so this module keeps the same hex-string representation to stay byte-for-byte
compatible:

* ``k = H(N || pad(g))`` (hard-coded in the JS)
* ``x = H(hex(s) || H(I ":" P))``
* ``u = H(pad(A) || pad(B))``
* ``S = (B - k * g^x) ^ (a + u * x) mod N``
* ``K = H(hex(S))``
* ``M1 = H((H(N) xor H(g)) || H(I) || s || A || B || K)``
* ``M2 = H(A || M1 || K)``
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .exceptions import VantivaAuthError

N_HEX = (
    "ac6bdb41324a9a9bf166de5e1389582faf72b6651987ee07fc3192943db56050a37329cbb4a099ed8193e07"
    "57767a13dd52312ab4b03310dcd7f48a9da04fd50e8083969edb767b0cf6095179a163ab3661a05fbd5faaae"
    "82918a9962f0b93b855f97993ec975eeaa80d740adbf4ff747359d041d5c33ea71d281e446b14773bca97b4"
    "3a23fb801676bd207a436c6481f1d2b9078717461a5b9d32e688f87748544523b524b0d57d5ea77a2775d2ec"
    "fa032cfbdbf52fb3786160279004e57ae6af874e7303ce53299ccc041c7bc308d82a5698f3a8d0c38271ae35"
    "f8e9dbfbb694b5c803d89f7ae435de236d525f54759b65e372fcd68ef20fa7111f9e4aff73"
)
N = int(N_HEX, 16)
G = 2
K_MULTIPLIER = int("05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300", 16)
# H(N) xor H(g), pre-computed in the router JS.
HNXORG_HEX = "4a76a9a2402bdd18123389b72ebbda50a30f65aedb90d7273130edea4b29cc4c"
PAD_BYTES = 256


def _h_hex(hex_string: str) -> str:
    """Hash the bytes encoded by ``hex_string`` (jsSHA "HEX" input)."""
    try:
        data = bytes.fromhex(hex_string)
    except ValueError as err:
        raise VantivaAuthError("Invalid hex in SRP exchange") from err
    return hashlib.sha256(data).hexdigest()


def _h_text(text: str) -> str:
    """Hash the UTF-8 encoding of ``text`` (jsSHA "TEXT" input after UTF-8 encoding)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _to_hex(value: int) -> str:
    """Return lower-case minimal hex padded to an even length, like the JS does."""
    hex_value = format(value, "x")
    return "0" + hex_value if len(hex_value) % 2 else hex_value


def _even(hex_string: str) -> str:
    """Left-pad a hex string to a whole number of bytes."""
    return "0" + hex_string if len(hex_string) % 2 else hex_string


def _pad(value: int) -> bytes:
    """Left-pad ``value`` to the group size in bytes."""
    return value.to_bytes(PAD_BYTES, "big")


class SrpClient:
    """Client side of the router's SRP-6a login."""

    __slots__ = ("_a", "_a_hex", "_m1", "_m2", "_password", "_session_key", "_username")

    def __init__(self, username: str, password: str, *, a: int | None = None) -> None:
        """Prepare an exchange; ``a`` may be fixed for tests, otherwise it is random."""
        self._username = username
        self._password = password
        self._a = a
        self._a_hex: str | None = None
        self._m1: str | None = None
        self._m2: str | None = None
        self._session_key: str | None = None

    def __repr__(self) -> str:
        """Return a representation that never includes secrets."""
        return f"SrpClient(username={self._username!r})"

    @property
    def session_key(self) -> str | None:
        """Return the shared session key ``K`` once the challenge has been processed."""
        return self._session_key

    def start(self) -> str:
        """Generate the ephemeral key pair and return ``A`` as hex."""
        while True:
            if self._a is None:
                self._a = secrets.randbits(256) or 1
            big_a = pow(G, self._a, N)
            if big_a % N != 0:
                break
            self._a = None  # pragma: no cover - astronomically unlikely
        self._a_hex = _to_hex(big_a)
        return self._a_hex

    def process_challenge(self, salt_hex: str, b_hex: str) -> str:
        """Process the server's salt and ``B`` and return the client proof ``M1`` as hex."""
        if self._a is None or self._a_hex is None:
            raise RuntimeError("start() must be called before process_challenge()")
        if not salt_hex or not b_hex:
            raise VantivaAuthError("Router sent an empty SRP challenge")
        try:
            big_b = int(b_hex, 16)
        except ValueError as err:
            raise VantivaAuthError("Router sent an invalid SRP challenge") from err
        # The JS would reject odd-length hex; pad to whole bytes instead (same byte value).
        salt_hex = _even(salt_hex.strip())
        b_hex = _even(b_hex.strip())
        big_a = int(self._a_hex, 16)
        u = int(hashlib.sha256(_pad(big_a) + _pad(big_b)).hexdigest(), 16)
        if big_b % N == 0 or u == 0:
            raise VantivaAuthError("Router sent an invalid SRP challenge")

        x = int(_h_hex(salt_hex + _h_text(f"{self._username}:{self._password}")), 16)
        g_x = (K_MULTIPLIER * pow(G, x, N)) % N
        exponent = (self._a + (u * x) % N) % N
        s = pow((big_b - g_x) % N, exponent, N)
        key = _h_hex(_to_hex(s))
        m1 = _h_hex(HNXORG_HEX + _h_text(self._username) + salt_hex + self._a_hex + b_hex + key)
        self._m2 = _h_hex(self._a_hex + m1 + key)
        self._m1 = m1
        self._session_key = key
        return m1

    def verify(self, m2_hex: str) -> bool:
        """Return True if ``m2_hex`` is the expected server proof (case-insensitive)."""
        if self._m2 is None:
            return False
        candidate = m2_hex.strip().lower().encode("utf-8")
        return hmac.compare_digest(self._m2.encode("ascii"), candidate)
