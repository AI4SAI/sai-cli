"""Short-lived Bearer selection and managed-node HMAC compatibility exchange."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
import secrets
import time
from typing import Callable, Mapping

from .cache import TokenCache, cache_key
from .config import Settings
from .errors import AuthenticationError, ContractError
from .transport import JsonTransport


@dataclass(frozen=True)
class TokenLease:
    token: str
    expires_at: int | None
    source: str


def _validate_token(value: object) -> str:
    if not isinstance(value, str):
        raise ContractError("the token response is invalid")
    token = value.strip()
    if not token or len(token) > 16_384 or any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise ContractError("the token response is invalid")
    return token


class TokenProvider:
    def __init__(
        self,
        *,
        settings: Settings,
        transport: JsonTransport,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.time,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.environ = os.environ if environ is None else environ
        self.clock = clock
        self.nonce_factory = nonce_factory or (lambda: secrets.token_hex(16))
        self.cache = TokenCache(
            settings.cache_path,
            enabled=settings.use_cache,
            clock=clock,
        )

    def _entry_key(self) -> str:
        if not self.settings.username:
            raise AuthenticationError(
                "missing SAI API username; set --username or SAI_API_USERNAME",
                code="credentials_unavailable",
            )
        return cache_key(
            base_url=self.settings.base_url,
            username=self.settings.username,
            key_id=self.settings.key_id,
        )

    def get(self, *, force_exchange: bool = False) -> TokenLease:
        direct = (self.environ.get("SAI_TOKEN") or "").strip()
        if direct:
            return TokenLease(token=_validate_token(direct), expires_at=None, source="environment")
        if self.settings.managed_login_node:
            raise AuthenticationError(
                "managed login nodes require an injected short-lived SAI_TOKEN",
                code="credentials_unavailable",
            )

        now = int(self.clock())
        entry_key = self._entry_key()
        if not force_exchange:
            cached = self.cache.get(entry_key, now=now)
            if cached:
                return TokenLease(token=cached[0], expires_at=cached[1], source="cache")
        return self._exchange(now=now, entry_key=entry_key)

    def invalidate(self, lease: TokenLease) -> None:
        if lease.source == "environment" or not self.settings.username:
            return
        self.cache.delete(self._entry_key())

    def _exchange(self, *, now: int, entry_key: str) -> TokenLease:
        if self.settings.managed_login_node:
            raise AuthenticationError(
                "managed login nodes require an injected short-lived SAI_TOKEN",
                code="credentials_unavailable",
            )
        username = self.settings.username or ""
        shared_secret = (self.environ.get("SAI_API_SHARED_SECRET") or "").strip()
        if not shared_secret:
            raise AuthenticationError(
                "no Bearer token or managed-node HMAC credential is available",
                code="credentials_unavailable",
            )
        nonce = self.nonce_factory()
        if (
            not nonce
            or len(nonce) > 128
            or any(ord(char) < 33 or ord(char) == 127 for char in nonce)
        ):
            raise AuthenticationError("the generated authentication nonce is invalid")
        canonical = f"{username}\n{now}\n{nonce}\n{self.settings.key_id}"
        signature = hmac.new(
            shared_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        response = self.transport.request(
            "POST",
            "/v1/token",
            query={
                "username": username,
                "ts": now,
                "nonce": nonce,
                "key_id": self.settings.key_id,
                "sig": signature,
            },
        )
        token = _validate_token(response.payload.get("token"))
        expires_at = response.payload.get("expires_at")
        if isinstance(expires_at, bool) or not isinstance(expires_at, int) or expires_at <= now:
            raise ContractError("the token response is invalid", request_id=response.request_id)
        self.cache.put(entry_key, token=token, expires_at=expires_at)
        return TokenLease(token=token, expires_at=expires_at, source="exchange")
