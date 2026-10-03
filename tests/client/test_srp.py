"""Known-answer tests for the SRP-6a client against an independent server implementation."""

from __future__ import annotations

import hashlib

import pytest
from custom_components.vantiva.vantiva_client import VantivaAuthError
from custom_components.vantiva.vantiva_client import srp as srp_module
from custom_components.vantiva.vantiva_client.srp import SrpClient
from tests.client.fake_router import G, N, SrpServer, int_bytes, k_value, pad, sha

USERNAME = "admin"
PASSWORD = "s3cret-Pässword"
SALT = bytes.fromhex("af1a0c75")
FIXED_A = 0x1D2C3B4A5968778695A4B3C2D1E0F00112233445566778899AABBCCDDEEFF0011
FIXED_B = 0x0F1E2D3C4B5A69788796A5B4C3D2E1F00123456789ABCDEF0123456789ABCDEF


def test_constants_match_rfc5054_derivation() -> None:
    assert int(srp_module.N_HEX, 16) == N
    assert k_value() == srp_module.K_MULTIPLIER
    h_xor = bytes(i ^ j for i, j in zip(sha(int_bytes(N)), sha(int_bytes(G)), strict=True))
    assert h_xor.hex() == srp_module.HNXORG_HEX


def test_known_answer_m1_and_m2() -> None:
    client = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
    a_hex = client.start()
    assert int(a_hex, 16) == pow(G, FIXED_A, N)
    assert len(a_hex) % 2 == 0
    assert a_hex == a_hex.lower()

    server = SrpServer(USERNAME, PASSWORD, SALT, b=FIXED_B)
    server.challenge(a_hex)
    m1 = client.process_challenge(server.salt_hex, server.b_hex)

    assert server.expected_m1 is not None and server.m2 is not None
    assert bytes.fromhex(m1) == server.expected_m1
    assert client.verify(server.m2.hex())
    assert client.verify(server.m2.hex().upper())
    assert client.verify(" " + server.m2.hex() + "\n")
    assert not client.verify("00" * 32)
    assert client.session_key is not None


def test_known_answer_is_deterministic() -> None:
    def run() -> str:
        client = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
        a_hex = client.start()
        server = SrpServer(USERNAME, PASSWORD, SALT, b=FIXED_B)
        server.challenge(a_hex)
        return client.process_challenge(server.salt_hex, server.b_hex)

    assert run() == run()


def test_known_answer_matches_hand_computed_values() -> None:
    """Spell out the router's formulas once more with plain hashlib on hex strings."""
    client = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
    a_hex = client.start()
    server = SrpServer(USERNAME, PASSWORD, SALT, b=FIXED_B)
    b_hex = server.b_hex
    salt_hex = server.salt_hex

    def h(hex_str: str) -> str:
        return hashlib.sha256(bytes.fromhex(hex_str)).hexdigest()

    a_int = int(a_hex, 16)
    b_int = int(b_hex, 16)
    u = int(hashlib.sha256(pad(a_int) + pad(b_int)).hexdigest(), 16)
    inner = hashlib.sha256(f"{USERNAME}:{PASSWORD}".encode()).hexdigest()
    x = int(h(salt_hex + inner), 16)
    s = pow((b_int - k_value() * pow(G, x, N)) % N, FIXED_A + u * x, N)
    s_hex = format(s, "x")
    s_hex = "0" + s_hex if len(s_hex) % 2 else s_hex
    key = h(s_hex)
    m1 = h(
        srp_module.HNXORG_HEX
        + hashlib.sha256(USERNAME.encode()).hexdigest()
        + salt_hex
        + a_hex
        + b_hex
        + key
    )
    assert client.process_challenge(salt_hex, b_hex) == m1
    assert client.verify(h(a_hex + m1 + key))


def test_wrong_password_gives_different_m1() -> None:
    server = SrpServer(USERNAME, PASSWORD, SALT, b=FIXED_B)
    good = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
    bad = SrpClient(USERNAME, PASSWORD + "x", a=FIXED_A)
    a_hex = good.start()
    assert bad.start() == a_hex
    server.challenge(a_hex)
    good_m1 = good.process_challenge(server.salt_hex, server.b_hex)
    bad_m1 = bad.process_challenge(server.salt_hex, server.b_hex)
    assert good_m1 != bad_m1
    assert server.expected_m1 is not None and server.m2 is not None
    assert bytes.fromhex(bad_m1) != server.expected_m1
    assert not bad.verify(server.m2.hex())


def test_random_a_round_trip() -> None:
    client = SrpClient(USERNAME, PASSWORD)
    a_hex = client.start()
    server = SrpServer(USERNAME, PASSWORD, SALT)
    server.challenge(a_hex)
    m1 = client.process_challenge(server.salt_hex, server.b_hex)
    assert server.expected_m1 is not None and server.m2 is not None
    assert bytes.fromhex(m1) == server.expected_m1
    assert client.verify(server.m2.hex())
    # Two clients pick different ephemeral keys.
    assert SrpClient(USERNAME, PASSWORD).start() != a_hex


def test_verify_before_challenge_is_false() -> None:
    client = SrpClient(USERNAME, PASSWORD)
    assert client.verify("00") is False
    assert client.session_key is None


def test_process_challenge_requires_start() -> None:
    with pytest.raises(RuntimeError):
        SrpClient(USERNAME, PASSWORD).process_challenge("00", "01")


@pytest.mark.parametrize(
    ("salt", "b_hex"),
    [
        ("", "01"),
        ("af1a0c75", ""),
        ("af1a0c75", "zz"),
        ("af1a0c75", format(N, "x")),  # B % N == 0
        ("af1a0c75", "00"),
        ("zz", "05"),  # not hex
    ],
)
def test_invalid_challenge_raises_auth_error(salt: str, b_hex: str) -> None:
    client = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
    client.start()
    with pytest.raises(VantivaAuthError):
        client.process_challenge(salt, b_hex)


def test_repr_hides_password() -> None:
    client = SrpClient(USERNAME, PASSWORD)
    assert PASSWORD not in repr(client)
    assert USERNAME in repr(client)


def test_odd_length_b_is_padded() -> None:
    """A B whose top nibble is zero gives the same proof with or without the leading 0."""
    b = 1
    while True:
        server = SrpServer(USERNAME, PASSWORD, SALT, b=b)
        if server.b_hex.startswith("0"):
            break
        b += 1
    client = SrpClient(USERNAME, PASSWORD, a=FIXED_A)
    a_hex = client.start()
    server.challenge(a_hex)
    server.odd_b_hex = True
    assert len(server.b_hex) % 2 == 1
    m1 = client.process_challenge(server.salt_hex, server.b_hex)
    assert server.expected_m1 is not None and server.m2 is not None
    assert bytes.fromhex(m1) == server.expected_m1
    assert client.verify(server.m2.hex())
