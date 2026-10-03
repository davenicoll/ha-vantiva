"""Single import point for the vendored Vantiva client library.

Every other module in the integration imports client symbols from here, so a later switch to a
PyPI package (or a test stand-in) only has to touch one place.
"""

from __future__ import annotations

from .vantiva_client import (
    GatewayInfo,
    GponStats,
    LanClient,
    VantivaAuthError,
    VantivaClient,
    VantivaConnectionError,
    VantivaData,
    VantivaError,
    VantivaLockedOutError,
    VantivaParseError,
    WanStatus,
)

__all__ = [
    "GatewayInfo",
    "GponStats",
    "LanClient",
    "VantivaAuthError",
    "VantivaClient",
    "VantivaConnectionError",
    "VantivaData",
    "VantivaError",
    "VantivaLockedOutError",
    "VantivaParseError",
    "WanStatus",
]
