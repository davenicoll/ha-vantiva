"""Exceptions raised by the Vantiva client library."""

from __future__ import annotations


class VantivaError(Exception):
    """Base class for all Vantiva client errors."""


class VantivaConnectionError(VantivaError):
    """The router could not be reached or returned a transport-level failure."""


class VantivaAuthError(VantivaError):
    """The router rejected the credentials or the login exchange."""


class VantivaLockedOutError(VantivaAuthError):
    """The router temporarily locked the account after repeated failed logins."""

    def __init__(
        self,
        wait_seconds: int | None = None,
        wrong_count: int | None = None,
        message: str | None = None,
    ) -> None:
        """Store the lockout details reported by the router."""
        self.wait_seconds = wait_seconds
        self.wrong_count = wrong_count
        if message is None:
            message = "Router locked the account after repeated failed logins"
            if wait_seconds is not None:
                message += f"; retry in {wait_seconds} s"
        super().__init__(message)


class VantivaParseError(VantivaError):
    """A page was fetched but its expected structure was missing."""
