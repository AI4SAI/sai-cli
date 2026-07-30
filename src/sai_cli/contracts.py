"""Allowlisted Portal job visibility response contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ContractError


JOB_ITEM_FIELDS = (
    "job_id",
    "array_task_id",
    "name",
    "slurm_user",
    "slurm_account",
    "state",
    "state_label",
    "priority",
    "submit_time",
    "start_time",
    "elapsed_seconds",
    "run_wait_seconds",
    "partition",
    "qos",
    "nodes",
    "slots",
    "gpus_per_node",
    "mem_per_unit",
    "reason_or_nodelist",
)

_TEXT_ITEM_FIELDS = {
    "array_task_id",
    "name",
    "slurm_user",
    "slurm_account",
    "state",
    "state_label",
    "submit_time",
    "start_time",
    "partition",
    "qos",
    "mem_per_unit",
    "reason_or_nodelist",
}
_INT_ITEM_FIELDS = {
    "priority",
    "elapsed_seconds",
    "run_wait_seconds",
    "nodes",
    "slots",
    "gpus_per_node",
}


def _required_text(payload: dict[str, Any], key: str, *, request_id: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 4096 or _has_unsafe_control(value):
        raise ContractError(request_id=request_id)
    return value


def _nullable_text(payload: dict[str, Any], key: str, *, request_id: str) -> str | None:
    if key not in payload:
        raise ContractError(request_id=request_id)
    value = payload[key]
    if value is not None and (
        not isinstance(value, str) or len(value) > 4096 or _has_unsafe_control(value)
    ):
        raise ContractError(request_id=request_id)
    return value


def _has_unsafe_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _nullable_int(payload: dict[str, Any], key: str, *, request_id: str) -> int | None:
    if key not in payload:
        raise ContractError(request_id=request_id)
    value = payload[key]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ContractError(request_id=request_id)
    return value


@dataclass(frozen=True)
class JobItem:
    values: dict[str, str | int | None]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "JobItem":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        values: dict[str, str | int | None] = {
            "job_id": _required_text(payload, "job_id", request_id=request_id),
        }
        for key in JOB_ITEM_FIELDS[1:]:
            if key in _TEXT_ITEM_FIELDS:
                values[key] = _nullable_text(payload, key, request_id=request_id)
            elif key in _INT_ITEM_FIELDS:
                values[key] = _nullable_int(payload, key, request_id=request_id)
            else:
                raise AssertionError(f"unclassified job field: {key}")
        return cls(values=values)

    def as_dict(self) -> dict[str, str | int | None]:
        return {key: self.values[key] for key in JOB_ITEM_FIELDS}


@dataclass(frozen=True)
class Freshness:
    source: str
    queried_at: str

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "Freshness":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        return cls(
            source=_required_text(payload, "source", request_id=request_id),
            queried_at=_required_text(payload, "queried_at", request_id=request_id),
        )

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "queried_at": self.queried_at}


@dataclass(frozen=True)
class JobResult:
    site_id: str
    cluster_id: str
    scope: str
    visibility_role: str
    slurm_user: str | None
    slurm_account: str | None
    items: tuple[JobItem, ...]
    freshness: Freshness

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "JobResult":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ContractError(request_id=request_id)
        count = payload.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(raw_items):
            raise ContractError(request_id=request_id)
        return cls(
            site_id=_required_text(payload, "site_id", request_id=request_id),
            cluster_id=_required_text(payload, "cluster_id", request_id=request_id),
            scope=_required_text(payload, "scope", request_id=request_id),
            visibility_role=_required_text(payload, "visibility_role", request_id=request_id),
            slurm_user=_nullable_text(payload, "slurm_user", request_id=request_id),
            slurm_account=_nullable_text(payload, "slurm_account", request_id=request_id),
            items=tuple(JobItem.from_payload(item, request_id=request_id) for item in raw_items),
            freshness=Freshness.from_payload(payload.get("freshness"), request_id=request_id),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "cluster_id": self.cluster_id,
            "scope": self.scope,
            "visibility_role": self.visibility_role,
            "slurm_user": self.slurm_user,
            "slurm_account": self.slurm_account,
            "items": [item.as_dict() for item in self.items],
            "count": len(self.items),
            "freshness": self.freshness.as_dict(),
        }
