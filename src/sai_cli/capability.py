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
from .errors import AuthenticationError, ConfigError, ContractError
from .managed_runs import clean_tasks_workspace
from .storage_summary import clean_workspace_key
from .transport import JsonTransport


CAPABILITY_HEADER = "X-SAI-Capability"
CAPABILITY_PATH = "/v1/authz/site-read"
CAPABILITY_SCHEMA = "sai-site-read-capability/v1"
CAPABILITY_AUDIENCE = "sai-site-read"
CAPABILITY_SURFACE = "site-read"
STORAGE_OPERATION = "storage.quota.read"
STORAGE_CAPABILITY_PATH = "/v1/authz/storage-read"
STORAGE_CAPABILITY_SCHEMA = "sai-storage-read-capability/v1"

_OPERATIONS = frozenset(
    {
        "jobs.list",
        "jobs.detail",
        "jobs.allocation",
        "jobs.placement",
        "billing.running-estimate",
    }
)
_SCOPES = frozenset(
    {"self", "personal_account", "org_account", "project_account"}
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
    base_url: str,
    user_token: str,
    request_body: Mapping[str, object],
    read_origin: str | None = None,
) -> str:
    """Bind the issuer, user, request and optional direct reader origin."""

    normalized = {
        "base_url": base_url.rstrip("/"),
        "audience": CAPABILITY_AUDIENCE,
        "surface": CAPABILITY_SURFACE,
        "user_token_sha256": hashlib.sha256(
            user_token.encode("utf-8")
        ).hexdigest(),
        "request": dict(request_body),
    }
    if read_origin is not None:
        normalized["read_origin"] = read_origin.rstrip("/")
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
        if not isinstance(request_body, Mapping):
            raise ContractError("the site-read capability request is invalid")
        body = dict(request_body)
        if body.get("operation") == STORAGE_OPERATION:
            if set(body) != {"operation", "site_id", "workspace_key"}:
                raise ContractError("the storage capability request is invalid")
            if not isinstance(body["site_id"], str) or not body["site_id"].strip():
                raise ContractError("the storage capability site is invalid")
            if clean_workspace_key(body["workspace_key"]) != body["workspace_key"]:
                raise ContractError("the storage capability workspace is invalid")
            return self._exchange(
                body, operation=STORAGE_OPERATION, user_lease=user_lease,
                force_refresh=force_refresh,
            )
        if set(body) not in (_REQUEST_FIELDS, _REQUEST_FIELDS | {"workspace_key"}):
            raise ContractError("the site-read capability request is invalid")
        operation = body.get("operation")
        if operation not in _OPERATIONS:
            raise ContractError("the requested capability operation is unsupported")
        if not isinstance(body.get("site_id"), str) or not body["site_id"].strip():
            raise ContractError("the site-read capability request is invalid")
        if not isinstance(body.get("cluster_id"), str) or not body["cluster_id"].strip():
            raise ContractError("the site-read capability request is invalid")
        if not isinstance(body.get("scope_type"), str) or not body["scope_type"].strip():
            raise ContractError("the site-read capability request is invalid")
        if body["scope_type"] not in _SCOPES:
            raise ContractError("the site-read capability request is invalid")
        workspace = body.get("workspace_key")
        if workspace is not None:
            try:
                workspace = clean_tasks_workspace(workspace)
            except ConfigError as exc:
                raise ContractError("the site-read capability workspace is invalid") from exc
            if workspace.split(":", 1)[0] + "_account" != body["scope_type"]:
                raise ContractError("the site-read capability workspace does not match its scope")
        selector_count = sum(body.get(key) is not None for key in (
            "slurm_account_id", "slurm_account_name", "workspace_key",
        ))
        if body["scope_type"] == "self":
            if selector_count:
                raise ContractError("the site-read capability request is invalid")
        elif selector_count != 1:
            raise ContractError("the site-read capability request is invalid")
        if any(
            not isinstance(body.get(field), (str, type(None)))
            for field in (
                "site_id",
                "cluster_id",
                "slurm_account_id",
                "slurm_account_name",
                "partition",
                "job_id",
            )
        ):
            raise ContractError("the site-read capability request is invalid")
        states = body.get("states")
        if (
            not isinstance(states, list)
            or any(not isinstance(state, str) for state in states)
            or states != sorted(set(states))
        ):
            raise ContractError("the site-read capability request is invalid")
        limit = body.get("limit")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500
        ):
            raise ContractError("the site-read capability request is invalid")
        if operation == "jobs.list" and (body.get("job_id") is not None or limit is None):
            raise ContractError("the site-read capability request is invalid")
        if operation in {"jobs.detail", "jobs.allocation", "jobs.placement"} and (
            body.get("job_id") is None
            or body.get("partition") is not None
            or limit is not None
        ):
            raise ContractError("the site-read capability request is invalid")
        if operation == "billing.running-estimate" and (
            body.get("job_id") is not None or limit is not None
        ):
            raise ContractError("the site-read capability request is invalid")
        return self._exchange(
            body, operation=operation, user_lease=user_lease,
            force_refresh=force_refresh,
        )

    def _exchange(
        self, body: dict[str, object], *, operation: str,
        user_lease: TokenLease, force_refresh: bool,
    ) -> CapabilityLease:
        if not isinstance(user_lease, TokenLease) or not user_lease.token:
            raise AuthenticationError(
                "the user session is unavailable",
                code="credentials_unavailable",
            )
        key = capability_cache_key(
            base_url=self.settings.base_url,
            user_token=user_lease.token,
            request_body=body,
            read_origin=(
                self.settings.site_read_base_url
                if operation in {"jobs.list", "jobs.detail", "jobs.allocation", "jobs.placement", STORAGE_OPERATION}
                else None
            ),
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
            STORAGE_CAPABILITY_PATH if operation == STORAGE_OPERATION else CAPABILITY_PATH,
            headers={"Authorization": f"Bearer {user_lease.token}"},
            json_body=({key: value for key, value in body.items() if key != "operation"}
                       if operation == STORAGE_OPERATION else body),
        )
        payload = response.payload
        if not isinstance(payload, Mapping):
            raise ContractError(
                "the site-read capability response is invalid",
                request_id=response.request_id,
            )
        required_echo = {
            "schema_version": STORAGE_CAPABILITY_SCHEMA if operation == STORAGE_OPERATION else CAPABILITY_SCHEMA,
            "audience": CAPABILITY_AUDIENCE,
            "surface": CAPABILITY_SURFACE,
            "operation": operation,
            "site_id": body.get("site_id"),
        }
        binding_field = "workspace_key" if operation == STORAGE_OPERATION else "cluster_id"
        required_echo[binding_field] = body.get(binding_field)
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
