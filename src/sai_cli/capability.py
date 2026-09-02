"""Opaque Portal capability bootstrap with protected short-lived caching."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Mapping

from .auth import TokenLease, _validate_token
from .cache import TokenCache
from .config import Settings
from .errors import AuthenticationError, ContractError
from .transport import JsonTransport


CAPABILITY_HEADER = "X-SAI-Capability"
CAPABILITY_PATH = "/v1/authz/site-read"
CAPABILITY_SCHEMA = "sai-site-read-capability/v1"
CAPABILITY_AUDIENCE = "sai-site-read"
CAPABILITY_SURFACE = "site-read"

_OPERATIONS = frozenset(
    {
        "jobs.list",
        "jobs.detail",
        "billing.running-estimate",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "operation",
        "site_id",
        "cluster_id",
        "scope_type",
        "slurm_account_id",
        "slurm_account_name",
        "partition",
        "states",
        "job_id",
        "limit",
    }
)


@dataclass(frozen=True)
class CapabilityLease:
    token: str
    expires_at: int
    source: str
    cache_key: str


def capability_cache_key(
    *,
    portal_base_url: str,
    site_read_base_url: str,
    user_token: str,
    request_body: Mapping[str, object],
) -> str:
    """Hash both trust origins and the complete exact authorization request."""

    normalized = {
        "portal_base_url": portal_base_url.rstrip("/"),
        "site_read_base_url": site_read_base_url.rstrip("/"),
        "audience": CAPABILITY_AUDIENCE,
        "surface": CAPABILITY_SURFACE,
        "user_token_sha256": hashlib.sha256(
            user_token.encode("utf-8")
        ).hexdigest(),
        "request": dict(request_body),
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "capability-" + hashlib.sha256(encoded).hexdigest()


class CapabilityProvider:
    def __init__(
        self,
        *,
        settings: Settings,
        portal_transport: JsonTransport,
        clock=time.time,
    ) -> None:
        self.settings = settings
        self.portal_transport = portal_transport
        self.clock = clock
        self.cache = TokenCache(
            settings.cache_path,
            enabled=settings.use_cache,
            clock=clock,
        )

    def get(
        self,
        *,
        request_body: Mapping[str, object],
        user_lease: TokenLease,
        force_refresh: bool = False,
    ) -> CapabilityLease:
        body = dict(request_body)
        if set(body) != _REQUEST_FIELDS:
            raise ContractError("the site-read capability request is invalid")
        operation = body.get("operation")
        if operation not in _OPERATIONS:
            raise ContractError("the requested capability operation is unsupported")
        if not isinstance(user_lease, TokenLease) or not user_lease.token:
            raise AuthenticationError(
                "the user session is unavailable",
                code="credentials_unavailable",
            )
        key = capability_cache_key(
            portal_base_url=self.settings.portal_base_url,
            site_read_base_url=self.settings.site_read_base_url,
            user_token=user_lease.token,
            request_body=body,
        )
        now = int(self.clock())
        if not force_refresh:
            cached = self.cache.get(key, now=now)
            if cached:
                return CapabilityLease(
                    token=cached[0],
                    expires_at=cached[1],
                    source="cache",
                    cache_key=key,
                )

        response = self.portal_transport.request(
            "POST",
            CAPABILITY_PATH,
            headers={"Authorization": f"Bearer {user_lease.token}"},
            json_body=body,
        )
        payload = response.payload
        required_echo = {
            "schema_version": CAPABILITY_SCHEMA,
            "audience": CAPABILITY_AUDIENCE,
            "surface": CAPABILITY_SURFACE,
            "operation": operation,
            "site_id": body.get("site_id"),
            "cluster_id": body.get("cluster_id"),
        }
        if any(payload.get(field) != value for field, value in required_echo.items()):
            raise ContractError(
                "the site-read capability response is invalid",
                request_id=response.request_id,
            )
        token = _validate_token(payload.get("capability"))
        expires_at = payload.get("expires_at")
        if (
            type(expires_at) is not int
            or expires_at <= now
            or expires_at - now > 300
        ):
            raise ContractError(
                "the site-read capability response is invalid",
                request_id=response.request_id,
            )
        self.cache.put(key, token=token, expires_at=expires_at)
        return CapabilityLease(
            token=token,
            expires_at=expires_at,
            source="exchange",
            cache_key=key,
        )

    def invalidate(self, lease: CapabilityLease) -> None:
        self.cache.delete(lease.cache_key)


__all__ = [
    "CAPABILITY_AUDIENCE",
    "CAPABILITY_HEADER",
    "CAPABILITY_PATH",
    "CAPABILITY_SCHEMA",
    "CAPABILITY_SURFACE",
    "CapabilityLease",
    "CapabilityProvider",
    "capability_cache_key",
]
