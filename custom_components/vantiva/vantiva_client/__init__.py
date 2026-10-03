"""Async client library for Vantiva (Technicolor) Homeware gateways.

Pure Python with ``aiohttp`` as the only dependency; no Home Assistant imports.
"""

from __future__ import annotations

from .client import VantivaClient
from .exceptions import (
    VantivaAuthError,
    VantivaConnectionError,
    VantivaError,
    VantivaLockedOutError,
    VantivaParseError,
)
from .models import ConnectionType, GatewayInfo, GponStats, LanClient, VantivaData, WanStatus

__all__ = [
    "ConnectionType",
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
