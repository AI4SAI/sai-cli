"""Credential selection for Portal calls and the SAI Identity device session."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import time
from typing import Callable, Mapping

try:  # pragma: no cover - Windows has no fcntl; atomic files still apply.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from .cache import (
    TokenCache,
    device_access_cache_key,
    device_pending_cache_key,
    device_refresh_cache_key,
)
from .config import Settings
from .errors import AuthenticationError, ContractError, SaiCliError
from .oidc import DeviceAuthorization, DeviceTokenResult, OidcClient
from .transport import JsonTransport


@dataclass(frozen=True)
class TokenLease:
    token: str
    expires_at: int | None
    source: str
    cache_key: str | None = None


def _validate_token(value: object) -> str:
    if not isinstance(value, str):
        raise ContractError("the token response is invalid")
    token = value.strip()
    if (
        not token
        or token != value
        or len(token) > 16_384
        or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in token)
    ):
        raise ContractError("the token response is invalid")
    return token


def _validate_device_result(result: DeviceTokenResult, *, now: int) -> DeviceTokenResult:
    if not isinstance(result, DeviceTokenResult):
        raise ContractError("the Identity token response is invalid")
    access_token = _validate_token(result.access_token)
    refresh_token = _validate_token(result.refresh_token)
    if (
        type(result.access_expires_at) is not int
        or result.access_expires_at <= now
        or result.access_expires_at - now > 60 * 60
        or (
            result.refresh_expires_at is not None
            and (
                type(result.refresh_expires_at) is not int
                or not now < result.refresh_expires_at <= 2**63 - 1
            )
        )
    ):
        raise ContractError("the Identity token response is invalid")
    for value, maximum in ((result.subject, 512), (result.device_id, 128)):
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ContractError("the Identity token response is invalid")
    return DeviceTokenResult(
        access_token=access_token,
        access_expires_at=result.access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=result.refresh_expires_at,
        subject=result.subject.strip() if result.subject else None,
        device_id=result.device_id.strip() if result.device_id else None,
    )


class TokenProvider:
    def __init__(
        self,
        *,
        settings: Settings,
        transport: JsonTransport,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.time,
        oidc_client: OidcClient | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.environ = os.environ if environ is None else environ
        self.clock = clock
        self.oidc_client = oidc_client
        self.cache = TokenCache(
            settings.cache_path,
            enabled=settings.use_cache,
            clock=clock,
        )
        self.credential_cache = TokenCache(
            settings.credential_path or settings.cache_path.with_name("credentials.json"),
            enabled=settings.use_cache,
            clock=clock,
        )

    def _device_cache_context(self) -> dict[str, str | None]:
        client = self.oidc_client
        return {
            "base_url": self.settings.base_url,
            "identity_issuer": client.issuer_url if client is not None else None,
            "client_id": client.client_id if client is not None else self.settings.oidc_client_id,
            "resource": client.resource if client is not None else self.settings.oidc_resource,
            "scope": client.scope if client is not None else self.settings.oidc_scope,
        }

    def _device_access_key(self) -> str:
        return device_access_cache_key(**self._device_cache_context())

    def _device_refresh_key(self) -> str:
        return device_refresh_cache_key(**self._device_cache_context())

    def _device_pending_key(self) -> str:
        return device_pending_cache_key(**self._device_cache_context())

    @contextmanager
    def _credential_lock(self):
        """Serialize rotating refresh exchanges across CLI processes."""

        path = self.credential_cache.path
        self.credential_cache._secure_parent()
        lock_path = path.with_name(f".{path.name}.lock")
        descriptor: int | None = None
        try:
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(lock_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise AuthenticationError("the SAI credential cache could not be locked") from exc
        finally:
            if descriptor is not None:
                if fcntl is not None:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(descriptor)

    def get(self, *, force_exchange: bool = False) -> TokenLease:
        direct = (self.environ.get("SAI_TOKEN") or "").strip()
        if direct:
            return TokenLease(token=_validate_token(direct), expires_at=None, source="environment")

        now = int(self.clock())
        access_key = self._device_access_key()
        if not force_exchange:
            cached = self.cache.get(access_key, now=now)
            if cached:
                return TokenLease(
                    token=cached[0],
                    expires_at=cached[1],
                    source="cache",
                    cache_key=access_key,
                )

        refresh = self.device_refresh(now=now)
        if refresh:
            return self._refresh_device(now=now)

        raise AuthenticationError(
            "no SAI Identity device session is available; run `sai auth login`",
            code="credentials_unavailable",
        )

    def invalidate(self, lease: TokenLease) -> None:
        if lease.source == "environment":
            return
        if lease.cache_key:
            self.cache.delete(lease.cache_key)
            return

    def install_device_tokens(self, result: DeviceTokenResult) -> None:
        """Persist an OIDC token response without exposing token values."""

        checked = _validate_device_result(result, now=int(self.clock()))
        if not self.settings.use_cache:
            raise AuthenticationError(
                "persistent device login requires the credential cache",
                code="credentials_unavailable",
            )
        with self._credential_lock():
            self._store_device_tokens_locked(checked)

    def _store_device_tokens_locked(self, result: DeviceTokenResult) -> None:
        self.credential_cache.put(
            self._device_refresh_key(),
            token=result.refresh_token,
            expires_at=result.refresh_expires_at,
            allow_unknown_expiry=True,
        )
        self.cache.put(
            self._device_access_key(),
            token=result.access_token,
            expires_at=result.access_expires_at,
        )

    def start_device_authorization(self) -> DeviceAuthorization:
        if self.oidc_client is None:
            raise AuthenticationError(
                "SAI Identity issuer is not configured; set SAI_IDENTITY_ISSUER",
                code="credentials_unavailable",
            )
        authorization = self.oidc_client.start_device_authorization(now=int(self.clock()))
        self.store_pending_device_code(
            device_code=authorization.device_code,
            expires_at=authorization.expires_at,
        )
        return authorization

    def poll_device_token(self, *, device_code: str) -> DeviceTokenResult | None:
        if self.oidc_client is None:
            raise AuthenticationError(
                "SAI Identity issuer is not configured; set SAI_IDENTITY_ISSUER",
                code="credentials_unavailable",
            )
        return self.oidc_client.poll_device_token(
            device_code=device_code,
            now=int(self.clock()),
        )

    def device_refresh(self, *, now: int | None = None) -> tuple[str, int | None] | None:
        current = int(self.clock()) if now is None else now
        return self.credential_cache.get(
            self._device_refresh_key(),
            now=current,
            margin_seconds=0,
            allow_unknown_expiry=True,
        )

    def store_pending_device_code(self, *, device_code: str, expires_at: int) -> None:
        if not self.settings.use_cache:
            raise AuthenticationError(
                "device login requires the credential cache",
                code="credentials_unavailable",
            )
        self.credential_cache.put(
            self._device_pending_key(),
            token=_validate_token(device_code),
            expires_at=expires_at,
        )

    def pending_device_code(self, *, now: int | None = None) -> tuple[str, int] | None:
        current = int(self.clock()) if now is None else now
        return self.credential_cache.get(
            self._device_pending_key(),
            now=current,
            margin_seconds=0,
        )

    def clear_pending_device_code(self) -> None:
        with self._credential_lock():
            self.credential_cache.delete(self._device_pending_key())

    def clear_device_credentials(self) -> None:
        with self._credential_lock():
            self._clear_device_credentials_locked()

    def _clear_device_credentials_locked(self) -> None:
        self.cache.delete(self._device_access_key())
        self.credential_cache.delete(self._device_refresh_key())
        self.credential_cache.delete(self._device_pending_key())

    def revoke_device(self) -> bool:
        # Hold the same lock as refresh/install so a concurrent rotation cannot
        # repopulate the local credential after logout.  Network failure must
        # not prevent local removal.
        with self._credential_lock():
            refresh = self.device_refresh()
            revoked = False
            if refresh and self.oidc_client is not None:
                try:
                    revoked = self.oidc_client.revoke(refresh_token=refresh[0])
                except SaiCliError:
                    # The server may be unreachable; local logout is still
                    # completed, while the caller reports server_revoked=false.
                    revoked = False
            self._clear_device_credentials_locked()
            return revoked

    def _refresh_device(self, *, now: int) -> TokenLease:
        if self.oidc_client is None:
            self.clear_device_credentials()
            raise AuthenticationError(
                "the SAI Identity issuer is not configured; run `sai auth login`",
                code="credentials_unavailable",
            )
        try:
            with self._credential_lock():
                cached = self.cache.get(self._device_access_key(), now=now)
                if cached:
                    return TokenLease(
                        token=cached[0],
                        expires_at=cached[1],
                        source="cache",
                        cache_key=self._device_access_key(),
                    )
                current = self.device_refresh(now=now)
                if not current:
                    raise AuthenticationError("the SAI device refresh credential is unavailable")
                result = _validate_device_result(
                    self.oidc_client.refresh(refresh_token=current[0], now=now),
                    now=now,
                )
                self._store_device_tokens_locked(result)
                return TokenLease(
                    token=result.access_token,
                    expires_at=result.access_expires_at,
                    source="cache",
                    cache_key=self._device_access_key(),
                )
        except (AuthenticationError, ContractError):
            self.clear_device_credentials()
            raise AuthenticationError(
                "the SAI Identity device session is no longer valid; run `sai auth login`",
                code="credentials_unavailable",
            )


__all__ = [
    "DeviceAuthorization",
    "DeviceTokenResult",
    "OidcClient",
    "TokenLease",
    "TokenProvider",
]
