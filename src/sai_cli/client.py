"""Exact CLI intent mapped to Portal issuance and site-read data requests."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote

from .auth import TokenLease, TokenProvider
from .capability import CAPABILITY_HEADER, CapabilityLease, CapabilityProvider
from .contracts import JobResult, RunningEstimateResult
from .errors import AuthenticationError, ConfigError, ContractError
from .transport import JsonResponse, JsonTransport


_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+-]*$")
_STATE_RE = re.compile(r"^[A-Z][A-Z0-9_+-]*$")
_SCOPES = {
    "self": "self",
    "personal-account": "personal_account",
    "org-account": "org_account",
    "project-account": "project_account",
}


def clean_token(
    value: str | None,
    *,
    field: str,
    required: bool = False,
    maximum: int = 128,
) -> str | None:
    text = (value or "").strip()
    if not text:
        if required:
            raise ConfigError(f"{field} is required")
        return None
    if len(text) > maximum or not _TOKEN_RE.fullmatch(text):
        raise ConfigError(f"{field} is invalid")
    return text


def clean_states(raw: str | None) -> tuple[str, ...]:
    states = {
        part.strip().upper()
        for part in (raw or "").split(",")
        if part.strip()
    }
    if len(states) > 32 or any(_STATE_RE.fullmatch(value) is None for value in states):
        raise ConfigError("states contains an invalid value")
    return tuple(sorted(states))


@dataclass(frozen=True)
class JobQuery:
    site_id: str
    cluster_id: str
    scope: str = "self"
    account_name: str | None = None
    account_id: str | None = None
    states: tuple[str, ...] = ()
    partition: str | None = None
    limit: int = 100

    def validated(self, *, detail: bool = False) -> JobQuery:
        site_id = clean_token(self.site_id, field="site", required=True, maximum=64) or ""
        cluster_id = (
            clean_token(self.cluster_id, field="cluster", required=True, maximum=64)
            or ""
        )
        if self.scope not in _SCOPES:
            raise ConfigError("scope is unsupported")
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
        if type(self.limit) is not int or not 1 <= self.limit <= 500:
            raise ConfigError("limit must be between 1 and 500")
        if detail and self.partition:
            raise ConfigError("jobs show does not accept a partition filter")
        return JobQuery(
            site_id=site_id,
            cluster_id=cluster_id,
            scope=self.scope,
            account_name=account_name,
            account_id=account_id,
            states=clean_states(",".join(self.states)),
            partition=clean_token(self.partition, field="partition", maximum=64),
            limit=self.limit,
        )

    def capability_request(
        self,
        *,
        operation: str,
        job_id: str | None = None,
    ) -> dict[str, object]:
        detail = operation == "jobs.detail"
        query = self.validated(detail=detail)
        if operation not in {"jobs.list", "jobs.detail", "billing.running-estimate"}:
            raise ConfigError("operation is unsupported")
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


class SaiClient:
    def __init__(
        self,
        *,
        portal_transport: JsonTransport,
        site_read_transport: JsonTransport,
        token_provider: TokenProvider,
        capability_provider: CapabilityProvider,
    ) -> None:
        self.portal_transport = portal_transport
        self.site_read_transport = site_read_transport
        self.token_provider = token_provider
        self.capability_provider = capability_provider

    def _site_read_get(
        self,
        path: str,
        *,
        capability_request: dict[str, object],
    ) -> JsonResponse:
        user_lease: TokenLease | None = None
        capability: CapabilityLease | None = None
        for attempt in range(2):
            try:
                user_lease = self.token_provider.get(force_exchange=attempt == 1)
                capability = self.capability_provider.get(
                    request_body=capability_request,
                    user_lease=user_lease,
                    force_refresh=attempt == 1,
                )
                return self.site_read_transport.request(
                    "GET",
                    path,
                    headers={CAPABILITY_HEADER: capability.token},
                )
            except AuthenticationError:
                if capability is not None:
                    self.capability_provider.invalidate(capability)
                if user_lease is not None:
                    self.token_provider.invalidate(user_lease)
                if attempt == 1:
                    raise
        raise ContractError("the site-read authentication retry budget was exhausted")

    def list_jobs(self, query: JobQuery) -> JobResult:
        request = query.capability_request(operation="jobs.list")
        response = self._site_read_get(
            "/v1/site-read/jobs",
            capability_request=request,
        )
        result = JobResult.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(
            site_id=request["site_id"],
            cluster_id=request["cluster_id"],
            scope_type=request["scope_type"],
            request_id=response.request_id,
        )
        return result

    def show_job(self, job_id: str, query: JobQuery) -> JobResult:
        clean_job_id = clean_token(
            job_id,
            field="job ID",
            required=True,
            maximum=128,
        ) or ""
        request = query.capability_request(
            operation="jobs.detail",
            job_id=clean_job_id,
        )
        response = self._site_read_get(
            f"/v1/site-read/jobs/{quote(clean_job_id, safe='')}",
            capability_request=request,
        )
        result = JobResult.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(
            site_id=request["site_id"],
            cluster_id=request["cluster_id"],
            scope_type=request["scope_type"],
            request_id=response.request_id,
        )
        if len(result.items) != 1:
            raise ContractError(
                "the job detail response must contain one item",
                request_id=response.request_id,
            )
        return result

    def running_estimates(self, query: JobQuery) -> RunningEstimateResult:
        request = query.capability_request(operation="billing.running-estimate")
        response = self._site_read_get(
            "/v1/site-read/billing/running-estimates",
            capability_request=request,
        )
        result = RunningEstimateResult.from_payload(
            response.payload,
            request_id=response.request_id,
        )
        result.require_request_binding(
            site_id=request["site_id"],
            cluster_id=request["cluster_id"],
            scope_type=request["scope_type"],
            request_id=response.request_id,
        )
        return result


__all__ = ["JobQuery", "SaiClient", "clean_states", "clean_token"]
