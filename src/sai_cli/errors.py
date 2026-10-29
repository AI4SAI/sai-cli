"""Bounded errors and stable process exit categories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_FORBIDDEN = 4
EXIT_NOT_FOUND = 5
EXIT_UNAVAILABLE = 6
EXIT_CONTRACT = 7
EXIT_NETWORK = 8


@dataclass(eq=False)
class SaiCliError(Exception):
    """An error safe to render without exposing a raw provider response."""

    code: str
    message: str
    exit_code: int
    request_id: str | None = None
    recovery_command: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.request_id:
            error["request_id"] = self.request_id
        return {"ok": False, "error": error}


class ConfigError(SaiCliError):
    def __init__(self, message: str, *, code: str = "configuration_invalid",
                 recovery_command: tuple[str, ...] = ()) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_USAGE, recovery_command=recovery_command)


class AuthenticationError(SaiCliError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "authentication_failed",
        request_id: str | None = None,
        recovery_command: tuple[str, ...] = (),
    ) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_AUTH, request_id=request_id,
                         recovery_command=recovery_command)


class ForbiddenError(SaiCliError):
    def __init__(self, message: str, *, code: str = "forbidden", request_id: str | None = None) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_FORBIDDEN, request_id=request_id)


class RefreshRejected(AuthenticationError):
    """The issuer explicitly rejected the refresh credential used in this request."""

    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__("the SAI Identity device session is no longer valid",
                         code="credentials_unavailable", request_id=request_id,
                         recovery_command=("auth", "login"))


class NotFoundError(SaiCliError):
    def __init__(self, message: str, *, code: str = "not_found", request_id: str | None = None) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_NOT_FOUND, request_id=request_id)


class UnavailableError(SaiCliError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "source_unavailable",
        request_id: str | None = None,
    ) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_UNAVAILABLE, request_id=request_id)


class ContractError(SaiCliError):
    def __init__(
        self,
        message: str = "the server returned an invalid response",
        *,
        code: str = "contract_invalid",
        request_id: str | None = None,
    ) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_CONTRACT, request_id=request_id)


class NetworkError(SaiCliError):
    def __init__(
        self,
        message: str = "the SAI API could not be reached",
        *,
        code: str = "network_unavailable",
        request_id: str | None = None,
    ) -> None:
        super().__init__(code=code, message=message, exit_code=EXIT_NETWORK, request_id=request_id)
