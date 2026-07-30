"""Mapping from explicit CLI scopes to Portal job visibility endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote

from .auth import TokenLease, TokenProvider
from .contracts import JobResult
from .errors import AuthenticationError, ConfigError
from .transport import JsonResponse, JsonTransport


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_STATE_RE = re.compile(r"^[A-Za-z0-9_+-]{1,32}$")
_SCOPES = {
    "self": "self",
    "personal-account": "personal_account",
    "org-account": "org_account",
    "project-account": "project_account",
}


def clean_token(value: str | None, *, field: str, required: bool = False, maximum: int = 128) -> str | None:
    text = (value or "").strip()
    if not text:
        if required:
            raise ConfigError(f"{field} is required")
        return None
    if len(text) > maximum or not _TOKEN_RE.fullmatch(text):
        raise ConfigError(f"{field} is invalid")
    return text


def clean_states(raw: str | None) -> tuple[str, ...]:
    states: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        token = part.strip().upper()
        if not token:
            continue
        if not _STATE_RE.fullmatch(token):
            raise ConfigError("states contains an invalid value")
        if token not in seen:
            seen.add(token)
            states.append(token)
    return tuple(states)


@dataclass(frozen=True)
class JobQuery:
    site_id: str
    scope: str = "self"
    cluster_id: str | None = None
    account_name: str | None = None
    account_id: str | None = None
    states: tuple[str, ...] = ()
    partition: str | None = None
    limit: int = 100

    def validated(self, *, detail: bool = False) -> "JobQuery":
        site_id = clean_token(self.site_id, field="site", required=True, maximum=64) or ""
        if self.scope not in _SCOPES:
            raise ConfigError("scope is unsupported")
        cluster_id = clean_token(self.cluster_id, field="cluster", maximum=64)
        account_name = clean_token(self.account_name, field="account", maximum=128)
        account_id = clean_token(self.account_id, field="account ID", maximum=64)
        if account_name and account_id:
            raise ConfigError("use either --account or --account-id, not both")
        if self.scope == "self" and (account_name or account_id):
            raise ConfigError("self scope does not accept an account selector")
        if self.scope in {"org-account", "project-account"} and not (account_name or account_id):
            raise ConfigError(f"{self.scope} requires --account or --account-id")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 500:
            raise ConfigError("limit must be between 1 and 500")
        if detail and self.partition:
            raise ConfigError("jobs show does not accept a partition filter")
        return JobQuery(
            site_id=site_id,
            scope=self.scope,
            cluster_id=cluster_id,
            account_name=account_name,
            account_id=account_id,
            states=tuple(clean_states(",".join(self.states))),
            partition=clean_token(self.partition, field="partition", maximum=64),
            limit=self.limit,
        )

    def parameters(self, *, detail: bool = False) -> dict[str, str | int | None]:
        query = self.validated(detail=detail)
        params: dict[str, str | int | None] = {
            "site_id": query.site_id,
            "cluster_id": query.cluster_id,
            "scope_type": _SCOPES[query.scope],
            "slurm_account_id": query.account_id,
            "slurm_account_name": query.account_name,
            "states": ",".join(query.states) or None,
            "source_preference": "live",
        }
        if not detail:
            params["partition"] = query.partition
            params["limit"] = query.limit
        return params


class PortalClient:
    def __init__(self, *, transport: JsonTransport, token_provider: TokenProvider) -> None:
        self.transport = transport
        self.token_provider = token_provider

    def _authorized_get(
        self,
        path: str,
        *,
        query: dict[str, str | int | None],
    ) -> JsonResponse:
        lease = self.token_provider.get()
        try:
            return self._get_with_lease(path, query=query, lease=lease)
        except AuthenticationError:
            if lease.source != "cache":
                raise
            self.token_provider.invalidate(lease)
            refreshed = self.token_provider.get(force_exchange=True)
            return self._get_with_lease(path, query=query, lease=refreshed)

    def _get_with_lease(
        self,
        path: str,
        *,
        query: dict[str, str | int | None],
        lease: TokenLease,
    ) -> JsonResponse:
        return self.transport.request(
            "GET",
            path,
            query=query,
            headers={"Authorization": f"Bearer {lease.token}"},
        )

    def list_jobs(self, query: JobQuery) -> JobResult:
        response = self._authorized_get("/v1/slurm/jobs", query=query.parameters())
        return JobResult.from_payload(response.payload, request_id=response.request_id)

    def show_job(self, job_id: str, query: JobQuery) -> JobResult:
        clean_job_id = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        path = f"/v1/slurm/jobs/{quote(clean_job_id, safe='')}"
        response = self._authorized_get(path, query=query.parameters(detail=True))
        result = JobResult.from_payload(response.payload, request_id=response.request_id)
        if len(result.items) != 1:
            from .errors import ContractError

            raise ContractError("the job detail response must contain one item", request_id=response.request_id)
        return result
