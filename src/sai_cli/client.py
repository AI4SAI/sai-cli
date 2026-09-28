"""Mapping from explicit CLI scopes to Portal read-only endpoints."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from urllib.parse import quote, urljoin

from .auth import TokenLease, TokenProvider
from .capability import CAPABILITY_HEADER, CapabilityLease, CapabilityProvider
from .catalog import ResourceCatalog
from .contracts import AccountStatus, JobResult, RunningEstimateResult
from .errors import AuthenticationError, ConfigError, ContractError
from .overview import AccountOverview
from .job_web_context import JobWebContext
from .managed_runs import (
    ManagedRunList, ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts, ManagedRunWorkspaces,
    clean_run_ref, clean_tasks_workspace,
)
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary, clean_workspace_key
from .native_quota import NativeQuotaResult
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

        detail = operation in {"jobs.detail", "jobs.allocation", "jobs.placement"}
        query = self.validated(detail=detail)
        if operation not in {"jobs.list", "jobs.detail", "jobs.allocation", "jobs.placement", "billing.running-estimate"}:
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
        site_transport: JsonTransport | None = None,
    ) -> None:
        if site_transport is not None and capability_provider is None:
            raise ConfigError("site reads require a Portal capability provider")
        self.transport = transport
        self.token_provider = token_provider
        self.capability_provider = capability_provider
        self.site_transport = site_transport

    @property
    def _cli_surface_enabled(self) -> bool:
        return self.capability_provider is not None

    def _acquire_capability(
        self, request_body: dict[str, object], *, lease: TokenLease,
        force_refresh: bool = False,
    ) -> tuple[TokenLease, CapabilityLease]:
        if self.capability_provider is None:
            raise ConfigError("site reads require a Portal capability provider")
        try:
            capability = self.capability_provider.get(
                request_body=request_body, user_lease=lease, force_refresh=force_refresh,
            )
        except AuthenticationError:
            if lease.source != "cache":
                raise
            self.token_provider.invalidate(lease)
            lease = self.token_provider.get(force_exchange=True)
            capability = self.capability_provider.get(
                request_body=request_body, user_lease=lease, force_refresh=True,
            )
        return lease, capability

    def _site_jobs(self, query: JobQuery, *, job_id: str | None = None) -> SiteJobResult:
        request = query.validated(detail=job_id is not None)
        operation = "jobs.detail" if job_id is not None else "jobs.list"
        body = request.capability_request(operation=operation, job_id=job_id)
        path = "/v1/site-read/jobs"
        if job_id is not None:
            path += "/" + quote(job_id, safe="")
        response = self._site_get(path, body=body)
        result = SiteJobResult.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(
            site_id=request.site_id, cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope], request_id=response.request_id,
            partition=request.partition, states=request.states,
            limit=request.limit if job_id is None else None, job_id=job_id,
            account_name=request.account_name,
            expected_source="scontrol" if job_id is not None else "squeue",
        )
        return result

    def _site_get(self, path: str, *, body: dict[str, object]) -> JsonResponse:
        if self.site_transport is None or self.capability_provider is None:
            raise ConfigError("native reads require a configured site_read_base_url and capability mode")
        lease, capability = self._acquire_capability(body, lease=self.token_provider.get())
        # The gateway receives only the capability. All filters are signed in it.
        try:
            response = self.site_transport.request(
                "GET", path, headers={CAPABILITY_HEADER: capability.token},
            )
        except AuthenticationError:
            if capability.source != "cache":
                raise
            self.capability_provider.invalidate(capability)
            _, capability = self._acquire_capability(body, lease=lease, force_refresh=True)
            response = self.site_transport.request(
                "GET", path, headers={CAPABILITY_HEADER: capability.token},
            )
        return response

    def job_allocation(self, job_id: str, query: JobQuery) -> SiteJobAllocationResult:
        identifier = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        if not re.fullmatch(r"[0-9]+(?:_[0-9]+)?", identifier):
            raise ConfigError("allocation requires a numeric job ID or numeric job_task ID")
        request = query.validated(detail=True)
        response = self._site_get(
            "/v1/site-read/jobs/" + quote(identifier, safe="") + "/allocation",
            body=request.capability_request(operation="jobs.allocation", job_id=identifier),
        )
        result = SiteJobAllocationResult.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(
            site_id=request.site_id, cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope], request_id=response.request_id,
            job_id=identifier, states=request.states, account_name=request.account_name,
        )
        return result

    def job_placement(self, job_id: str, query: JobQuery) -> SiteJobPlacementResult:
        identifier = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        if not re.fullmatch(r"[0-9]+(?:_[0-9]+)?", identifier):
            raise ConfigError("placement requires a numeric job ID or numeric job_task ID")
        request = query.validated(detail=True)
        response = self._site_get(
            "/v1/site-read/jobs/" + quote(identifier, safe="") + "/placement",
            body=request.capability_request(operation="jobs.placement", job_id=identifier),
        )
        result = SiteJobPlacementResult.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(
            site_id=request.site_id, cluster_id=request.cluster_id, scope=_SCOPES[request.scope],
            request_id=response.request_id, job_id=identifier, states=request.states, account_name=request.account_name,
        )
        return result

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
            lease, capability = self._acquire_capability(request_body, lease=lease)
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

    def account_status(self, *, lease: TokenLease) -> AccountStatus:
        response = self._get_with_lease("/v1/account/cli/status", query={}, lease=lease)
        result = AccountStatus.from_payload(response.payload, request_id=response.request_id)
        return replace(result, verification_url=urljoin(self.transport.base_url, result.verification_url))

    def account_overview(self, site_id: str, *, account: str | None = None) -> AccountOverview:
        site = clean_token(site_id, field="site", required=True)
        selected = clean_token(account, field="account")
        response = self._central_get("/v1/account/cli/overview",
            query={"site_id": site, "slurm_account_name": selected})
        return AccountOverview.from_payload(response.payload, site_id=site, account=selected,
                                            request_id=response.request_id)

    def job_web_context(self, job_id: str, query: JobQuery) -> JobWebContext:
        identifier = clean_token(job_id, field="job ID", required=True, maximum=128) or ""
        if not re.fullmatch(r"[0-9]+(?:_[0-9]+)?", identifier):
            raise ConfigError("Web navigation requires a numeric job ID or numeric job_task ID")
        request = query.validated()
        response = self._central_get("/v1/slurm/cli/jobs/" + quote(identifier, safe="") + "/web-context", query={
            "site_id": request.site_id, "cluster_id": request.cluster_id, "scope_type": _SCOPES[request.scope],
            "slurm_account_id": request.account_id, "slurm_account_name": request.account_name,
            "source_preference": "live",
        })
        result = JobWebContext.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(site_id=request.site_id, cluster_id=request.cluster_id, scope=_SCOPES[request.scope],
                                       account_id=request.account_id, job_id=identifier, request_id=response.request_id)
        return result

    def _central_get(self, path: str, *, query: dict[str, str | int | None]) -> JsonResponse:
        """Read a central resource without obtaining or forwarding a site grant."""
        lease = self.token_provider.get()
        try:
            return self._get_with_lease(path, query=query, lease=lease)
        except AuthenticationError:
            if lease.source != "cache":
                raise
            self.token_provider.invalidate(lease)
            lease = self.token_provider.get(force_exchange=True)
            return self._get_with_lease(path, query=query, lease=lease)

    def list_run_workspaces(self, *, site_id: str, limit: int = 50,
                            cursor: str | None = None) -> ManagedRunWorkspaces:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ConfigError("project page limit must be between 1 and 100")
        if cursor is not None:
            clean_tasks_workspace(cursor)
        site = clean_token(site_id, field="site", required=True, maximum=64)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", site) is None or site.casefold() in {"default", "global"}:
            raise ConfigError("site must identify a configured site")
        response = self._central_get("/v1/compute/cli/workspaces", query={"site_id": site, "limit": limit, "cursor": cursor})
        return ManagedRunWorkspaces.from_payload(response.payload, site_id=site, limit=limit,
                                                cursor=cursor, request_id=response.request_id)

    def _managed_read(self, *, workspace_key: str, site_id: str, run_ref: str | None = None,
                      suffix: str = "", **parameters: str | int | None) -> JsonResponse:
        workspace = clean_tasks_workspace(workspace_key)
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        path = "/v1/compute/cli/runs"
        if run_ref is not None:
            path += "/" + quote(clean_run_ref(run_ref), safe="") + suffix
        return self._central_get(path, query={"workspace_key": workspace, "site_id": site, **parameters})

    def list_managed_runs(self, *, workspace_key: str, site_id: str, limit: int = 50,
                          cursor: str | None = None) -> ManagedRunList:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ConfigError("run limit must be between 1 and 100")
        if cursor is not None:
            clean_run_ref(cursor)
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, limit=limit, cursor=cursor)
        return ManagedRunList.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                          limit=limit, cursor=cursor, request_id=response.request_id)

    def managed_run(self, run_ref: str, *, workspace_key: str, site_id: str) -> ManagedRunDetail:
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref)
        return ManagedRunDetail.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                            run_ref=run_ref, request_id=response.request_id)

    def managed_run_logs(self, run_ref: str, *, workspace_key: str, site_id: str, stream: str = "stdout",
                         cursor: str | None = None, max_bytes: int = 65536) -> ManagedRunLogs:
        if stream not in {"stdout", "stderr"}:
            raise ConfigError("log stream must be stdout or stderr")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
            raise ConfigError("log max_bytes must be between 1 and 65536")
        if cursor is not None and (not isinstance(cursor, str) or re.fullmatch(rf"log-{stream}-(?:0|[1-9][0-9]{{0,18}})", cursor) is None
                                   or int(cursor.rsplit("-", 1)[1]) > 2**63 - 1):
            raise ConfigError("log cursor is invalid for this stream")
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref, suffix="/logs",
                                      stream=stream, cursor=cursor, max_bytes=max_bytes)
        return ManagedRunLogs.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                          run_ref=run_ref, stream=stream, cursor=cursor, max_bytes=max_bytes, request_id=response.request_id)

    def managed_run_artifacts(self, run_ref: str, *, workspace_key: str, site_id: str,
                             cursor: str | None = None, limit: int = 100) -> ManagedRunArtifacts:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ConfigError("output file limit must be between 1 and 100")
        if cursor is not None and (not isinstance(cursor, str) or re.fullmatch(r"0|[1-9][0-9]{0,8}", cursor) is None):
            raise ConfigError("output file cursor is invalid")
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref, suffix="/artifacts",
                                      cursor=cursor, limit=limit)
        return ManagedRunArtifacts.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                               run_ref=run_ref, cursor=cursor, limit=limit, request_id=response.request_id)
    def resource_catalog(self, site_id: str) -> ResourceCatalog:
        site = clean_token(site_id, field="site", required=True)
        prefix = "/v1/account/cli/sites" if self._cli_surface_enabled else "/v1/account/sites"
        path = f"{prefix}/{quote(site, safe='')}/resource-catalog"
        response = self._central_get(path, query={})
        return ResourceCatalog.from_payload(response.payload, site_id=site, request_id=response.request_id)

    def storage_quota_summary(self, *, workspace_key: str, site_id: str) -> StorageQuotaSummary:
        workspace = clean_workspace_key(workspace_key)
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        path = "/v1/account/cli/storage/quota-summary"
        query = {"workspace_key": workspace, "site_id": site}
        response = self._central_get(path, query=query)
        return StorageQuotaSummary.from_payload(
            response.payload,
            workspace_key=workspace,
            site_id=site,
            request_id=response.request_id,
        )

    def storage_native_quota(self, *, workspace_key: str, site_id: str) -> NativeQuotaResult:
        workspace = clean_workspace_key(workspace_key)
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        response = self._site_get(
            "/v1/site-read/storage/native-quota",
            body={"operation": "storage.quota.read", "workspace_key": workspace, "site_id": site},
        )
        return NativeQuotaResult.from_payload(
            response.payload, workspace_key=workspace, site_id=site,
            request_id=response.request_id,
        )

    def list_jobs(self, query: JobQuery) -> JobResult | SiteJobResult:
        if self.site_transport is not None:
            return self._site_jobs(query)
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

    def show_job(self, job_id: str, query: JobQuery) -> JobResult | SiteJobResult:
        clean_job_id = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        if self.site_transport is not None:
            return self._site_jobs(query, job_id=clean_job_id)
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
        if len(result.items) != 1 or result.items[0].canonical_id != clean_job_id:
            raise ContractError(
                "the job detail response must contain the requested job",
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
