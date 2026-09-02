"""Mapping from explicit CLI scopes to Portal read-only endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote

from .auth import TokenLease, TokenProvider
from .capability import CAPABILITY_HEADER, CapabilityLease, CapabilityProvider
from .contracts import JobResult, RunningEstimateResult
from .errors import AuthenticationError, ConfigError, ContractError
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
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"{field} is invalid")
    text = (value or "").strip()
    if not text:
        if required:
            raise ConfigError(f"{field} is required")
        return None
    if len(text) > maximum or not _TOKEN_RE.fullmatch(text):
        raise ConfigError(f"{field} is invalid")
    return text


def clean_states(raw: str | None) -> tuple[str, ...]:
    if raw is not None and not isinstance(raw, str):
        raise ConfigError("states contains an invalid value")
    states = {
        part.strip().upper()
        for part in (raw or "").split(",")
        if part.strip()
    }
    if len(states) > 32 or any(
        _STATE_RE.fullmatch(value) is None for value in states
    ):
        raise ConfigError("states contains an invalid value")
    return tuple(sorted(states))


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
        if not isinstance(self.scope, str):
            raise ConfigError("scope is unsupported")
        if not isinstance(self.states, tuple) or any(
            not isinstance(state, str) for state in self.states
        ):
            raise ConfigError("states contains an invalid value")
        site_id = clean_token(self.site_id, field="site", required=True, maximum=64) or ""
        if self.scope not in _SCOPES:
            raise ConfigError("scope is unsupported")
        cluster_id = clean_token(self.cluster_id, field="cluster", maximum=64)
        account_name = clean_token(self.account_name, field="account", maximum=64)
        account_id = clean_token(self.account_id, field="account ID", maximum=64)
        if account_name and account_id:
            raise ConfigError("use either --account or --account-id, not both")
        if self.scope == "self" and (account_name or account_id):
            raise ConfigError("self scope does not accept an account selector")
        if self.scope in {"personal-account", "org-account", "project-account"} and not (
            account_name or account_id
        ):
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

    def parameters(
        self,
        *,
        detail: bool = False,
        include_limit: bool = True,
    ) -> dict[str, str | int | None]:
        if detail and not include_limit:
            raise ConfigError("detail queries cannot disable the limit contract")
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
        if not detail and include_limit:
            params["partition"] = query.partition
            params["limit"] = query.limit
        elif not detail:
            params["partition"] = query.partition
        return params

    def capability_request(
        self,
        *,
        operation: str,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Build the exact JSON body consumed by Portal's capability issuer."""

        detail = operation == "jobs.detail"
        query = self.validated(detail=detail)
        if operation not in {"jobs.list", "jobs.detail", "billing.running-estimate"}:
            raise ConfigError("operation is unsupported")
        if query.cluster_id is None:
            raise ConfigError(
                "cluster is required when site-read capability mode is enabled"
            )
        clean_job_id = (
            clean_token(job_id, field="job ID", required=detail, maximum=128)
            if detail
            else None
        )
        return {
            "operation": operation,
            "site_id": query.site_id,
            "cluster_id": query.cluster_id,
            "scope_type": _SCOPES[query.scope],
            "slurm_account_id": query.account_id,
            "slurm_account_name": query.account_name,
            "partition": None if detail else query.partition,
            "states": list(query.states),
            "job_id": clean_job_id,
            "limit": query.limit if operation == "jobs.list" else None,
        }


class PortalClient:
    def __init__(
        self,
        *,
        transport: JsonTransport,
        token_provider: TokenProvider,
        capability_provider: CapabilityProvider | None = None,
    ) -> None:
        self.transport = transport
        self.token_provider = token_provider
        self.capability_provider = capability_provider

    @property
    def _cli_surface_enabled(self) -> bool:
        return self.capability_provider is not None

    def _authorized_get(
        self,
        path: str,
        *,
        query: dict[str, str | int | None],
        operation: str,
        capability_request: dict[str, object] | None = None,
        job_id: str | None = None,
    ) -> JsonResponse:
        lease = self.token_provider.get()
        capability: CapabilityLease | None = None
        if self.capability_provider is not None:
            request_body = capability_request or {
                "operation": operation,
                "site_id": query.get("site_id"),
                "cluster_id": query.get("cluster_id"),
                "scope_type": query.get("scope_type"),
                "slurm_account_id": query.get("slurm_account_id"),
                "slurm_account_name": query.get("slurm_account_name"),
                "partition": query.get("partition"),
                "states": [],
                "job_id": job_id,
                "limit": query.get("limit"),
            }
            try:
                capability = self.capability_provider.get(
                    request_body=request_body,
                    user_lease=lease,
                )
            except AuthenticationError:
                # A cached Portal bearer may have expired while the capability
                # bootstrap is being attempted.  Refresh that bearer once,
                # then obtain a capability for the new actor session.
                if lease.source != "cache":
                    raise
                self.token_provider.invalidate(lease)
                lease = self.token_provider.get(force_exchange=True)
                capability = self.capability_provider.get(
                    request_body=request_body,
                    user_lease=lease,
                    force_refresh=True,
                )
        try:
            return self._get_with_lease(
                path,
                query=query,
                lease=lease,
                capability=capability,
            )
        except AuthenticationError:
            if capability is not None and capability.source == "cache":
                self.capability_provider.invalidate(capability)
                refreshed_capability = self.capability_provider.get(
                    request_body=request_body,
                    user_lease=lease,
                    force_refresh=True,
                )
                return self._get_with_lease(
                    path,
                    query=query,
                    lease=lease,
                    capability=refreshed_capability,
                )
            if lease.source != "cache":
                raise
            self.token_provider.invalidate(lease)
            refreshed = self.token_provider.get(force_exchange=True)
            refreshed_capability = (
                self.capability_provider.get(
                    request_body=request_body,
                    user_lease=refreshed,
                    force_refresh=True,
                )
                if self.capability_provider is not None
                else None
            )
            return self._get_with_lease(
                path,
                query=query,
                lease=refreshed,
                capability=refreshed_capability,
            )

    def _get_with_lease(
        self,
        path: str,
        *,
        query: dict[str, str | int | None],
        lease: TokenLease,
        capability: CapabilityLease | None = None,
    ) -> JsonResponse:
        headers = {"Authorization": f"Bearer {lease.token}"}
        if capability is not None:
            headers[CAPABILITY_HEADER] = capability.token
        return self.transport.request(
            "GET",
            path,
            query=query,
            headers=headers,
        )

    def list_jobs(self, query: JobQuery) -> JobResult:
        path = "/v1/slurm/cli/jobs" if self._cli_surface_enabled else "/v1/slurm/jobs"
        capability_request = (
            query.capability_request(operation="jobs.list")
            if self._cli_surface_enabled
            else None
        )
        response = self._authorized_get(
            path,
            query=query.parameters(),
            operation="jobs.list",
            capability_request=capability_request,
        )
        result = JobResult.from_payload(
            response.payload,
            request_id=response.request_id,
        )
        request = query.validated()
        result.require_request_binding(
            site_id=request.site_id,
            cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope],
            request_id=response.request_id,
        )
        return result

    def show_job(self, job_id: str, query: JobQuery) -> JobResult:
        clean_job_id = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        prefix = "/v1/slurm/cli/jobs" if self._cli_surface_enabled else "/v1/slurm/jobs"
        path = f"{prefix}/{quote(clean_job_id, safe='')}"
        capability_request = (
            query.capability_request(
                operation="jobs.detail",
                job_id=clean_job_id,
            )
            if self._cli_surface_enabled
            else None
        )
        response = self._authorized_get(
            path,
            query=query.parameters(detail=True),
            operation="jobs.detail",
            capability_request=capability_request,
            job_id=clean_job_id,
        )
        result = JobResult.from_payload(response.payload, request_id=response.request_id)
        request = query.validated(detail=True)
        result.require_request_binding(
            site_id=request.site_id,
            cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope],
            request_id=response.request_id,
        )
        if len(result.items) != 1:
            raise ContractError(
                "the job detail response must contain one item",
                request_id=response.request_id,
            )
        return result

    def running_estimates(self, query: JobQuery) -> RunningEstimateResult:
        capability_request = (
            query.capability_request(operation="billing.running-estimate")
            if self._cli_surface_enabled
            else None
        )
        response = self._authorized_get(
            "/v1/billing/cli/running-estimates"
            if self._cli_surface_enabled
            else "/v1/billing/running-estimates",
            # Portal's running-estimate contract consumes the complete
            # authorized queue snapshot and deliberately has no paging
            # ``limit`` parameter.  Keep the user's limit local so it cannot
            # drift into an unsupported server query key.
            query=query.parameters(include_limit=False),
            operation="billing.running-estimate",
            capability_request=capability_request,
        )
        result = RunningEstimateResult.from_payload(
            response.payload,
            request_id=response.request_id,
        )
        request = query.validated()
        result.require_request_binding(
            site_id=request.site_id,
            cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope],
            request_id=response.request_id,
        )
        return result


SaiClient = PortalClient


__all__ = [
    "JobQuery",
    "PortalClient",
    "SaiClient",
    "clean_states",
    "clean_token",
]
