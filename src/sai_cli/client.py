"""Mapping from explicit CLI scopes to Portal read-only endpoints."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Callable
import re
from urllib.parse import quote, urljoin

from .auth import TokenLease, TokenProvider
from .capability import CAPABILITY_HEADER, CapabilityLease, CapabilityProvider
from .catalog import ResourceCatalog
from .contracts import AccountStatus, JobCostResult, JobResult, RunningEstimateResult, short_job_state
from .errors import AuthenticationError, ConfigError, ContractError
from .overview import AccountOverview
from .default_account import DefaultAccountChange, DefaultAccountState
from .job_web_context import JobWebContext
from .artifact_content import ManagedRunArtifactContent, ARTIFACT, content_cursor
from .artifact_download import ArtifactDownloadGrant, download_artifact
from .managed_runs import (
    ManagedRunList, MyManagedRunList, ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts, ManagedRunWorkspaces,
    clean_run_ref, clean_tasks_workspace,
)
from .run_cost import ManagedRunCost
from .run_stats import ManagedRunStats
from .run_placement import ManagedRunPlacement
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary, StorageWorkspaces, clean_workspace_key
from .workspace_page import workspace_page_query
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
    workspace_key: str | None = None

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
        workspace = clean_tasks_workspace(self.workspace_key) if self.workspace_key is not None else None
        if account_name and account_id:
            raise ConfigError("use either --account or --account-id, not both")
        if workspace is not None and (account_name or account_id):
            raise ConfigError("use --workspace-key, --account, or --account-id, not more than one")
        if self.scope == "self" and (account_name or account_id or workspace):
            raise ConfigError("self scope does not accept an account selector")
        if workspace is not None and self.scope != workspace.split(":", 1)[0] + "-account":
            raise ConfigError("workspace kind must match --scope")
        if self.scope in {"personal-account", "org-account", "project-account"} and not (
            account_name or account_id or workspace
        ):
            raise ConfigError(f"{self.scope} requires --workspace-key, --account, or --account-id")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 500:
            raise ConfigError("limit must be between 1 and 500")
        if detail and self.partition:
            raise ConfigError("a single-job read does not accept a partition filter")
        return JobQuery(
            site_id=site_id,
            scope=self.scope,
            cluster_id=cluster_id,
            account_name=account_name,
            account_id=account_id,
            states=tuple(clean_states(",".join(self.states))),
            partition=clean_token(self.partition, field="partition", maximum=64),
            limit=self.limit,
            workspace_key=workspace,
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
        if query.workspace_key is not None:
            params["workspace_key"] = query.workspace_key
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
        body: dict[str, object] = {
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
        if query.workspace_key is not None:
            body["workspace_key"] = query.workspace_key
        return body


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
        result.require_current(request_id=response.request_id)
        return result

    def _authorized_get(
        self,
        path: str,
        *,
        query: dict[str, str | int | None],
        capability_request: dict[str, object] | None,
    ) -> JsonResponse:
        lease = self.token_provider.get()
        capability: CapabilityLease | None = None
        if self.capability_provider is not None:
            if capability_request is None:
                raise ContractError("the site-read capability request is missing")
            request_body = capability_request
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
            **({"workspace_key": request.workspace_key} if request.workspace_key is not None else {}),
        })
        result = JobWebContext.from_payload(response.payload, request_id=response.request_id)
        result.require_request_binding(site_id=request.site_id, cluster_id=request.cluster_id, scope=_SCOPES[request.scope],
                                       account_id=request.account_id, workspace_key=request.workspace_key,
                                       job_id=identifier, request_id=response.request_id)
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
                            cursor: str | None = None, workspace_key: str | None = None) -> ManagedRunWorkspaces:
        site = clean_token(site_id, field="site", required=True, maximum=64)
        query = workspace_page_query(site_id=site, limit=limit, cursor=cursor,
                                      workspace_key=workspace_key, clean_workspace=clean_tasks_workspace)
        response = self._central_get("/v1/compute/cli/workspaces", query=query)
        return ManagedRunWorkspaces.from_payload(response.payload, site_id=site, limit=limit,
            cursor=cursor, workspace_key=workspace_key, request_id=response.request_id)

    def list_storage_workspaces(self, *, site_id: str, limit: int = 50,
                               cursor: str | None = None, workspace_key: str | None = None) -> StorageWorkspaces:
        site = clean_token(site_id, field="site", required=True, maximum=64)
        query = workspace_page_query(site_id=site, limit=limit, cursor=cursor,
                                      workspace_key=workspace_key, clean_workspace=clean_workspace_key)
        response = self._central_get("/v1/account/cli/storage/workspaces", query=query)
        return StorageWorkspaces.from_payload(response.payload, site_id=site, limit=limit,
            cursor=cursor, workspace_key=workspace_key, request_id=response.request_id)

    def account_defaults(self, site_id: str) -> DefaultAccountState:
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        response = self._central_get("/v1/account/cli/defaults", query={"site_id": site})
        return DefaultAccountState.from_payload(response.payload, site_id=site, request_id=response.request_id)

    def set_default_account(self, account_id: str | None, *, expected_account_id: str | None,
                            idempotency_key: str) -> DefaultAccountChange:
        target = clean_token(account_id, field="account ID", required=account_id is not None, maximum=64)
        expected = clean_token(expected_account_id, field="expected account ID",
                               required=expected_account_id is not None, maximum=64)
        key = clean_token(idempotency_key, field="request ID", required=True) or ""
        if len(key) < 8:
            raise ConfigError("request ID must contain 8-128 characters")
        lease = self.token_provider.get()
        response = self.transport.request(
            "PUT", "/v1/account/cli/defaults",
            headers={"Authorization": f"Bearer {lease.token}", "Idempotency-Key": key},
            json_body={"account_id": target, "expected_account_id": expected},
        )
        return DefaultAccountChange.from_payload(
            response.payload, account_id=target, expected_account_id=expected,
            idempotency_key=key, request_id=response.request_id,
        )

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

    def list_my_managed_runs(self, *, site_id: str, limit: int = 50,
                             cursor: str | None = None, run_refs: tuple[str, ...] | None = None,
                             workspace_key: str | None = None) -> MyManagedRunList:
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ConfigError("run limit must be between 1 and 100")
        if cursor is not None:
            clean_run_ref(cursor)
        if run_refs is not None and (cursor is not None or not 1 <= len(run_refs) <= min(limit, 100) or len(set(run_refs)) != len(run_refs)
                or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value) is None for value in run_refs)):
            raise ConfigError("exact Run references are invalid")
        if workspace_key is not None:
            if run_refs is None:
                raise ConfigError("workspace narrowing requires exact Run references")
            clean_tasks_workspace(workspace_key)
        response = self._central_get("/v1/compute/cli/my-runs", query={"site_id": site, "limit": limit, "cursor": cursor,
            "run_refs": ",".join(run_refs) if run_refs is not None else None, "workspace_key": workspace_key})
        result = MyManagedRunList.from_payload(response.payload, site_id=site, limit=limit,
                                               cursor=cursor, request_id=response.request_id)
        if run_refs is not None and (result.values["has_more"] or any(
                row["run_ref"] not in run_refs or workspace_key is not None and row["workspace_key"] != workspace_key
                for row in result.values["items"])):
            raise ContractError(request_id=response.request_id)
        return result

    def managed_run(self, run_ref: str, *, workspace_key: str, site_id: str) -> ManagedRunDetail:
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref)
        return ManagedRunDetail.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                            run_ref=run_ref, request_id=response.request_id)

    def managed_run_placement(self, run_ref: str, *, workspace_key: str, site_id: str) -> ManagedRunPlacement:
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref, suffix="/placement")
        result = ManagedRunPlacement.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                                 run_ref=run_ref, request_id=response.request_id)
        result.placement.require_current(request_id=response.request_id)
        return result

    def managed_run_stats(self, run_ref: str, *, workspace_key: str, site_id: str) -> ManagedRunStats:
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref, suffix="/stats")
        return ManagedRunStats.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
                                           run_ref=run_ref, request_id=response.request_id)

    def managed_run_cost(self, run_ref: str, *, workspace_key: str, site_id: str) -> ManagedRunCost:
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref, suffix="/billing")
        return ManagedRunCost.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
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

    def managed_run_artifact_content(self, run_ref: str, *, workspace_key: str, site_id: str,
                                     artifact_ref: str, artifact_cursor: str | None = None,
                                     cursor: str | None = None) -> ManagedRunArtifactContent:
        if not isinstance(artifact_ref, str) or ARTIFACT.fullmatch(artifact_ref) is None:
            raise ConfigError("artifact reference is invalid")
        if artifact_cursor is not None and (not isinstance(artifact_cursor, str) or re.fullmatch(r"0|[1-9][0-9]{0,8}", artifact_cursor) is None):
            raise ConfigError("artifact list cursor is invalid")
        content_cursor(cursor)
        response = self._managed_read(workspace_key=workspace_key, site_id=site_id, run_ref=run_ref,
            suffix=f"/artifacts/{artifact_ref}/content", artifact_cursor=artifact_cursor, cursor=cursor)
        return ManagedRunArtifactContent.from_payload(response.payload, workspace_key=workspace_key, site_id=site_id,
            run_ref=run_ref, artifact_ref=artifact_ref, cursor=cursor, request_id=response.request_id)

    def download_managed_run_artifact(self, run_ref: str, *, workspace_key: str, site_id: str,
                                      artifact_ref: str, output: str,
                                      artifact_cursor: str | None = None,
                                      cancelled: Callable[[], bool] | None = None) -> dict[str, object]:
        workspace = clean_tasks_workspace(workspace_key)
        site = clean_token(site_id, field="site", required=True, maximum=64) or ""
        run = clean_run_ref(run_ref)
        if not isinstance(artifact_ref, str) or ARTIFACT.fullmatch(artifact_ref) is None:
            raise ConfigError("artifact reference is invalid")
        if artifact_cursor is not None and (not isinstance(artifact_cursor, str)
                or re.fullmatch(r"0|[1-9][0-9]{0,8}", artifact_cursor) is None):
            raise ConfigError("artifact list cursor is invalid")
        path = f"/v1/compute/cli/runs/{quote(run, safe='')}/artifacts/{artifact_ref}/download"

        def acquire(version: str | None) -> ArtifactDownloadGrant:
            lease = self.token_provider.get()
            for attempt in range(2):
                try:
                    response = self.transport.request("POST", path,
                        headers={"Authorization": f"Bearer {lease.token}"}, json_body={
                            "workspace_key": workspace, "site_id": site,
                            "artifact_cursor": artifact_cursor, "version": version,
                        })
                    break
                except AuthenticationError:
                    if attempt or lease.source != "cache":
                        raise
                    self.token_provider.invalidate(lease)
                    lease = self.token_provider.get(force_exchange=True)
            return ArtifactDownloadGrant.from_payload(response.payload, workspace_key=workspace,
                site_id=site, run_ref=run, artifact_ref=artifact_ref, version=version)

        return download_artifact(output=output, acquire=acquire, timeout_seconds=self.transport.timeout_seconds,
            workspace_key=workspace, site_id=site, run_ref=run, artifact_ref=artifact_ref, cancelled=cancelled)

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
            capability_request=capability_request,
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

    def job_cost(self, job_id: str, query: JobQuery) -> JobCostResult:
        clean_job_id = clean_token(job_id, field="job ID", required=True, maximum=64) or ""
        request = query.validated(detail=True)
        prefix = "/v1/slurm/cli/jobs" if self._cli_surface_enabled else "/v1/slurm/jobs"
        response = self._authorized_get(
            f"{prefix}/{quote(clean_job_id, safe='')}",
            query={**request.parameters(detail=True), "include_estimate": "true"},
            capability_request=(request.capability_request(operation="jobs.detail", job_id=clean_job_id)
                                if self._cli_surface_enabled else None),
        )
        result = JobCostResult.from_payload(response.payload, request_id=response.request_id)
        result.observation.require_request_binding(
            site_id=request.site_id, cluster_id=request.cluster_id,
            scope=_SCOPES[request.scope], request_id=response.request_id,
        )
        job = result.observation.items[0]
        if (job.canonical_id != clean_job_id
                or (request.account_name is not None and job.values["slurm_account"] != request.account_name)
                or (request.states and short_job_state(job.values["state"]) not in
                    {short_job_state(state) for state in request.states})):
            raise ContractError("the cost response must contain the requested job", request_id=response.request_id)
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
