"""Allowlisted native job observations and their request binding."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .contracts import (
    JobItem,
    _nullable_int,
    _nullable_nonempty_text,
    _nullable_sha256_text,
    _required_bool,
    _required_int,
    _required_text,
    _timestamp_text,
    _validate_subject,
)
from .errors import ContractError


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
_SCOPES = {"self", "personal_account", "org_account", "project_account"}
_STATE_SHORT = {
    "RUNNING": "R",
    "PENDING": "PD",
    "COMPLETING": "CG",
    "SUSPENDED": "S",
    "COMPLETED": "CD",
    "FAILED": "F",
    "CANCELLED": "CA",
}
_JOB_TEXT_LIMITS = {
    "name": 4096,
    "reason_or_nodelist": 4096,
    "state": 32,
    "submit_time": 64,
    "start_time": 64,
}


@dataclass(frozen=True)
class SiteJobFreshness:
    source: str
    observed_at: str
    ttl_seconds: int
    age_seconds: int
    stale: bool

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "SiteJobFreshness":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        source = _required_text(payload, "source", request_id=request_id)
        observed_at = _timestamp_text(payload, "observed_at", request_id=request_id, nullable=False)
        ttl = _required_int(payload, "ttl_seconds", request_id=request_id)
        age = _required_int(payload, "age_seconds", request_id=request_id)
        stale = _required_bool(payload, "stale", request_id=request_id)
        if (
            source not in {"squeue", "scontrol"}
            or observed_at is None
            or len(observed_at) > 64
            or stale != (age >= ttl)
        ):
            raise ContractError(request_id=request_id)
        return cls(source, observed_at, ttl, age, stale)

    def as_dict(self) -> dict[str, str | int | bool]:
        return {
            "source": self.source,
            "observed_at": self.observed_at,
            "ttl_seconds": self.ttl_seconds,
            "age_seconds": self.age_seconds,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class _SiteJobContext:
    site_id: str
    cluster_id: str
    scope_type: str
    slurm_user: str | None
    slurm_account: str | None
    freshness: SiteJobFreshness
    etag: str

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "_SiteJobContext":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        subject = payload.get("subject")
        if not isinstance(subject, dict):
            raise ContractError(request_id=request_id)
        site = _required_text(payload, "site_id", request_id=request_id, maximum=128)
        cluster = _required_text(payload, "cluster_id", request_id=request_id, maximum=128)
        scope = _required_text(payload, "scope_type", request_id=request_id, maximum=32)
        user = _nullable_nonempty_text(subject, "slurm_user", request_id=request_id, maximum=128)
        account = _nullable_nonempty_text(subject, "slurm_account", request_id=request_id, maximum=128)
        if scope not in _SCOPES or any(
            value is not None and _TOKEN_RE.fullmatch(value) is None
            for value in (site, cluster, user, account)
        ):
            raise ContractError(request_id=request_id)
        _validate_subject(scope=scope, slurm_user=user, slurm_account=account, request_id=request_id)
        etag = _nullable_sha256_text(payload, "etag", request_id=request_id)
        if etag is None:
            raise ContractError(request_id=request_id)
        return cls(
            site, cluster, scope, user, account,
            SiteJobFreshness.from_payload(payload.get("freshness"), request_id=request_id),
            etag,
        )

    def read_job(self, payload: object, *, request_id: str) -> JobItem:
        item = JobItem.from_payload(payload, request_id=request_id, text_limits=_JOB_TEXT_LIMITS)
        values = item.values
        if (self.slurm_user is not None and values["slurm_user"] != self.slurm_user) or (
            self.slurm_account is not None and values["slurm_account"] != self.slurm_account
        ):
            raise ContractError(request_id=request_id)
        for key in ("slurm_user", "slurm_account", "state"):
            _required_text(values, key, request_id=request_id, maximum=128)
        for key in ("submit_time", "start_time"):
            _timestamp_text(values, key, request_id=request_id, nullable=True)
        return item

    def require_request_binding(
        self,
        *,
        site_id: str,
        cluster_id: str,
        scope: str,
        request_id: str,
        expected_source: str | None = None,
        account_name: str | None = None,
    ) -> None:
        if (
            (self.site_id, self.cluster_id, self.scope_type) != (site_id, cluster_id, scope)
            or (expected_source is not None and self.freshness.source != expected_source)
            or (account_name is not None and self.slurm_account != account_name)
        ):
            raise ContractError(request_id=request_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "cluster_id": self.cluster_id,
            "scope_type": self.scope_type,
            "subject": {"slurm_user": self.slurm_user, "slurm_account": self.slurm_account},
            "freshness": self.freshness.as_dict(),
            "etag": self.etag,
        }


@dataclass(frozen=True)
class SiteJobResult(_SiteJobContext):
    items: tuple[JobItem, ...]
    has_more: bool

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "SiteJobResult":
        if not isinstance(payload, dict) or payload.get("schema_version") != "jobs/v1":
            raise ContractError(request_id=request_id)
        context = _SiteJobContext.from_payload(payload, request_id=request_id)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or len(raw_items) > 500:
            raise ContractError(request_id=request_id)
        return cls(
            **vars(context),
            items=tuple(context.read_job(item, request_id=request_id) for item in raw_items),
            has_more=_required_bool(payload, "has_more", request_id=request_id),
        )

    def require_request_binding(
        self, *, partition: str | None = None, states: tuple[str, ...] = (),
        limit: int | None = None, job_id: str | None = None, **context: Any,
    ) -> None:
        super().require_request_binding(**context)
        request_id = context["request_id"]
        if ((limit is not None and len(self.items) > limit)
                or (job_id is not None and (len(self.items) != 1 or self.has_more))):
            raise ContractError(request_id=request_id)
        allowed_states = {_STATE_SHORT.get(state, state) for state in states}
        for item in self.items:
            values = item.values
            if ((partition is not None and values["partition"] != partition)
                    or (allowed_states and values["state"] not in allowed_states)
                    or (job_id is not None and values["job_id"] != job_id)):
                raise ContractError(request_id=request_id)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "jobs/v1", **super().as_dict(),
                "has_more": self.has_more, "items": [item.as_dict() for item in self.items]}


@dataclass(frozen=True)
class SiteAllocationNode:
    name: str
    cpus: int
    memory_mib: int | None

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "SiteAllocationNode":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        name = _required_text(payload, "name", request_id=request_id, maximum=128)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise ContractError(request_id=request_id)
        return cls(name, _required_int(payload, "cpus", request_id=request_id),
                   _nullable_int(payload, "memory_mib", request_id=request_id))


@dataclass(frozen=True)
class SiteJobAllocationResult(_SiteJobContext):
    job: JobItem
    restart_count: int | None
    scheduler_states: tuple[str, ...]
    allocation_status: str
    nodes: tuple[SiteAllocationNode, ...] | None

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "SiteJobAllocationResult":
        if not isinstance(payload, dict) or payload.get("schema_version") != "jobs.allocation/v1":
            raise ContractError(request_id=request_id)
        context = _SiteJobContext.from_payload(payload, request_id=request_id)
        job = context.read_job(payload.get("job"), request_id=request_id)
        if not re.fullmatch(r"[0-9]+", job.values["job_id"]) or (
            job.values["array_task_id"] is not None
            and not re.fullmatch(r"[0-9]+", job.values["array_task_id"])
        ):
            raise ContractError(request_id=request_id)
        restart_count = _nullable_int(payload, "restart_count", request_id=request_id)
        if restart_count is not None and restart_count > 65535:
            raise ContractError(request_id=request_id)
        states = payload.get("scheduler_states")
        allocation = payload.get("allocation")
        if (not isinstance(states, list) or not 1 <= len(states) <= 32
                or any(not isinstance(state, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", state)
                       for state in states)
                or not isinstance(allocation, dict)):
            raise ContractError(request_id=request_id)
        if _STATE_SHORT.get(states[0], states[0]) != job.values["state"]:
            raise ContractError(request_id=request_id)
        status = _required_text(allocation, "status", request_id=request_id)
        if "nodes" not in allocation:
            raise ContractError(request_id=request_id)
        nodes = allocation["nodes"]
        if status == "unavailable":
            if nodes is not None:
                raise ContractError(request_id=request_id)
        elif status in {"allocated", "not_allocated"}:
            if (not isinstance(nodes, list) or len(nodes) > 4096
                    or bool(nodes) != (status == "allocated")):
                raise ContractError(request_id=request_id)
        else:
            raise ContractError(request_id=request_id)
        parsed_nodes = None if nodes is None else tuple(
            SiteAllocationNode.from_payload(node, request_id=request_id) for node in nodes
        )
        if parsed_nodes and len({node.name for node in parsed_nodes}) != len(parsed_nodes):
            raise ContractError(request_id=request_id)
        return cls(
            **vars(context), job=job, restart_count=restart_count,
            scheduler_states=tuple(states), allocation_status=status, nodes=parsed_nodes,
        )

    def require_request_binding(
        self, *, job_id: str, states: tuple[str, ...] = (), **context: Any,
    ) -> None:
        super().require_request_binding(expected_source="scontrol", **context)
        values = self.job.values
        identity = values["job_id"]
        if values["array_task_id"] is not None:
            identity = f"{identity}_{values['array_task_id']}"
        allowed_states = {_STATE_SHORT.get(state, state) for state in states}
        if identity != job_id or (allowed_states and values["state"] not in allowed_states):
            raise ContractError(request_id=context["request_id"])

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "jobs.allocation/v1", **super().as_dict(),
                "job": self.job.as_dict(), "restart_count": self.restart_count,
                "scheduler_states": list(self.scheduler_states),
                "allocation": {"status": self.allocation_status,
                               "nodes": None if self.nodes is None else [
                                   {"name": node.name, "cpus": node.cpus, "memory_mib": node.memory_mib}
                                   for node in self.nodes]}}
