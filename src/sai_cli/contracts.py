"""Allowlisted Portal job visibility and running-estimate contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

RUNNING_ESTIMATE_ITEM_FIELDS = (
    "job_key",
    "job_id_raw",
    "slurm_job_db_index",
    "slurm_user",
    "slurm_account",
    "state",
    "submit_time",
    "start_time",
    "elapsed_seconds",
    "resources",
    "gross_cny",
    "cash_cny",
    "currency",
    "price_revision",
    "estimate_status",
    "uncertainty",
    "final",
)
RUNNING_ESTIMATE_RESOURCE_FIELDS = (
    "partition",
    "qos",
    "nodes",
    "alloc_tres",
    "resource_type",
    "resource_count",
    "usage_quantity",
)
RUNNING_ESTIMATE_ALLOC_TRES_FIELDS = (
    "gpu",
    "cpu",
    "mem_mb",
    "billing",
    "nodes",
)

_DECIMAL_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_MONEY_RE = re.compile(r"^[0-9]+\.[0-9]{8}$")
_MACHINE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_ESTIMATE_STATUSES = {"estimated", "partial", "not_started", "unavailable"}
_RESOURCE_TYPES = {"gpu", "cpu"}

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


def _required_int(payload: dict[str, Any], key: str, *, request_id: str) -> int:
    value = _nullable_int(payload, key, request_id=request_id)
    if value is None:
        raise ContractError(request_id=request_id)
    return value


def _required_bool(payload: dict[str, Any], key: str, *, request_id: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ContractError(request_id=request_id)
    return value


def _required_false(payload: dict[str, Any], key: str, *, request_id: str) -> bool:
    value = _required_bool(payload, key, request_id=request_id)
    if value is not False:
        raise ContractError(request_id=request_id)
    return value


def _nullable_nonempty_text(payload: dict[str, Any], key: str, *, request_id: str) -> str | None:
    value = _nullable_text(payload, key, request_id=request_id)
    if value is not None and not value.strip():
        raise ContractError(request_id=request_id)
    return value


def _literal_text(
    payload: dict[str, Any],
    key: str,
    *,
    expected: str,
    request_id: str,
) -> str:
    value = _required_text(payload, key, request_id=request_id)
    if value != expected:
        raise ContractError(request_id=request_id)
    return value


def _decimal_text(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    nullable: bool,
    money: bool = False,
) -> str | None:
    value = _nullable_nonempty_text(payload, key, request_id=request_id)
    if value is None:
        if nullable:
            return None
        raise ContractError(request_id=request_id)
    pattern = _MONEY_RE if money else _DECIMAL_RE
    if len(value) > 128 or pattern.fullmatch(value) is None:
        raise ContractError(request_id=request_id)
    return value


def _timestamp_text(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    nullable: bool,
) -> str | None:
    value = _nullable_nonempty_text(payload, key, request_id=request_id)
    if value is None:
        if nullable:
            return None
        raise ContractError(request_id=request_id)
    if "T" not in value or not value.endswith("Z"):
        raise ContractError(request_id=request_id)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(request_id=request_id) from exc
    if parsed.tzinfo is None:
        raise ContractError(request_id=request_id)
    return value


def _iana_timezone(payload: dict[str, Any], key: str, *, request_id: str) -> str:
    value = _required_text(payload, key, request_id=request_id)
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ContractError(request_id=request_id) from exc
    return value


def _machine_codes(payload: dict[str, Any], key: str, *, request_id: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list) or len(values) > 100:
        raise ContractError(request_id=request_id)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or _MACHINE_CODE_RE.fullmatch(value) is None:
            raise ContractError(request_id=request_id)
        result.append(value)
    return tuple(result)


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


def _running_estimate_alloc_tres(payload: object, *, request_id: str) -> dict[str, str | int | None]:
    if not isinstance(payload, dict):
        raise ContractError(request_id=request_id)
    mem_mb = _decimal_text(payload, "mem_mb", request_id=request_id, nullable=False)
    return {
        "gpu": _required_int(payload, "gpu", request_id=request_id),
        "cpu": _required_int(payload, "cpu", request_id=request_id),
        "mem_mb": mem_mb or "",
        "billing": _decimal_text(payload, "billing", request_id=request_id, nullable=True),
        "nodes": _required_int(payload, "nodes", request_id=request_id),
    }


def _running_estimate_resources(payload: object, *, request_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or "alloc_tres" not in payload:
        raise ContractError(request_id=request_id)
    resource_type = _nullable_nonempty_text(payload, "resource_type", request_id=request_id)
    if resource_type is not None and resource_type not in _RESOURCE_TYPES:
        raise ContractError(request_id=request_id)
    raw_alloc_tres = payload["alloc_tres"]
    return {
        "partition": _nullable_nonempty_text(payload, "partition", request_id=request_id),
        "qos": _nullable_nonempty_text(payload, "qos", request_id=request_id),
        "nodes": _nullable_int(payload, "nodes", request_id=request_id),
        "alloc_tres": (
            None
            if raw_alloc_tres is None
            else _running_estimate_alloc_tres(raw_alloc_tres, request_id=request_id)
        ),
        "resource_type": resource_type,
        "resource_count": _nullable_int(payload, "resource_count", request_id=request_id),
        "usage_quantity": _decimal_text(
            payload,
            "usage_quantity",
            request_id=request_id,
            nullable=True,
        ),
    }


@dataclass(frozen=True)
class RunningEstimateItem:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "RunningEstimateItem":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        estimate_status = _required_text(payload, "estimate_status", request_id=request_id)
        if estimate_status not in _ESTIMATE_STATUSES:
            raise ContractError(request_id=request_id)
        values: dict[str, Any] = {
            "job_key": _nullable_nonempty_text(payload, "job_key", request_id=request_id),
            "job_id_raw": _nullable_nonempty_text(payload, "job_id_raw", request_id=request_id),
            "slurm_job_db_index": _nullable_int(payload, "slurm_job_db_index", request_id=request_id),
            "slurm_user": _nullable_nonempty_text(payload, "slurm_user", request_id=request_id),
            "slurm_account": _nullable_nonempty_text(payload, "slurm_account", request_id=request_id),
            "state": _nullable_nonempty_text(payload, "state", request_id=request_id),
            "submit_time": _timestamp_text(payload, "submit_time", request_id=request_id, nullable=True),
            "start_time": _timestamp_text(payload, "start_time", request_id=request_id, nullable=True),
            "elapsed_seconds": _nullable_int(payload, "elapsed_seconds", request_id=request_id),
            "resources": _running_estimate_resources(payload.get("resources"), request_id=request_id),
            "gross_cny": _decimal_text(payload, "gross_cny", request_id=request_id, nullable=True, money=True),
            "cash_cny": _decimal_text(payload, "cash_cny", request_id=request_id, nullable=True, money=True),
            "currency": _literal_text(payload, "currency", expected="CNY", request_id=request_id),
            "price_revision": _nullable_nonempty_text(payload, "price_revision", request_id=request_id),
            "estimate_status": estimate_status,
            "uncertainty": list(_machine_codes(payload, "uncertainty", request_id=request_id)),
            "final": _required_false(payload, "final", request_id=request_id),
        }
        resources = values["resources"]
        priced_values = (
            values["gross_cny"],
            values["price_revision"],
            resources["resource_type"],
            resources["resource_count"],
            resources["usage_quantity"],
        )
        if estimate_status == "estimated" and (
            values["cash_cny"] is None
            or any(value is None for value in priced_values)
            or values["uncertainty"]
        ):
            raise ContractError(request_id=request_id)
        if estimate_status == "partial" and (
            values["cash_cny"] is not None
            or any(value is None for value in priced_values)
            or not values["uncertainty"]
        ):
            raise ContractError(request_id=request_id)
        if estimate_status in {"not_started", "unavailable"} and any(
            value is not None
            for value in (
                values["gross_cny"],
                values["cash_cny"],
                values["price_revision"],
                resources["resource_type"],
                resources["resource_count"],
                resources["usage_quantity"],
            )
        ):
            raise ContractError(request_id=request_id)
        if estimate_status == "unavailable" and not values["uncertainty"]:
            raise ContractError(request_id=request_id)
        return cls(values=values)

    def as_dict(self) -> dict[str, Any]:
        return {key: self.values[key] for key in RUNNING_ESTIMATE_ITEM_FIELDS}


@dataclass(frozen=True)
class RunningEstimateFreshness:
    source: str
    observed_at: str
    ttl_seconds: int
    age_seconds: int
    stale: bool

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "RunningEstimateFreshness":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        observed_at = _timestamp_text(payload, "observed_at", request_id=request_id, nullable=False)
        return cls(
            source=_required_text(payload, "source", request_id=request_id),
            observed_at=observed_at or "",
            ttl_seconds=_required_int(payload, "ttl_seconds", request_id=request_id),
            age_seconds=_required_int(payload, "age_seconds", request_id=request_id),
            stale=_required_bool(payload, "stale", request_id=request_id),
        )

    def as_dict(self) -> dict[str, str | int | bool]:
        return {
            "source": self.source,
            "observed_at": self.observed_at,
            "ttl_seconds": self.ttl_seconds,
            "age_seconds": self.age_seconds,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class RunningEstimateResult:
    operation: str
    version: str
    schema_version: str
    site_id: str
    site_timezone: str
    cluster_id: str
    scope: str
    visibility_role: str
    slurm_user: str | None
    slurm_account: str | None
    as_of: str
    freshness: RunningEstimateFreshness
    etag: str
    items: tuple[RunningEstimateItem, ...]
    final: bool

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "RunningEstimateResult":
        if not isinstance(payload, dict):
            raise ContractError(request_id=request_id)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ContractError(request_id=request_id)
        count = payload.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(raw_items):
            raise ContractError(request_id=request_id)
        as_of = _timestamp_text(payload, "as_of", request_id=request_id, nullable=False)
        return cls(
            operation=_literal_text(
                payload,
                "operation",
                expected="billing.running-estimate",
                request_id=request_id,
            ),
            version=_literal_text(payload, "version", expected="v1", request_id=request_id),
            schema_version=_literal_text(
                payload,
                "schema_version",
                expected="billing.running-estimate/v1",
                request_id=request_id,
            ),
            site_id=_required_text(payload, "site_id", request_id=request_id),
            site_timezone=_iana_timezone(payload, "site_timezone", request_id=request_id),
            cluster_id=_required_text(payload, "cluster_id", request_id=request_id),
            scope=_required_text(payload, "scope", request_id=request_id),
            visibility_role=_required_text(payload, "visibility_role", request_id=request_id),
            slurm_user=_nullable_nonempty_text(payload, "slurm_user", request_id=request_id),
            slurm_account=_nullable_nonempty_text(payload, "slurm_account", request_id=request_id),
            as_of=as_of or "",
            freshness=RunningEstimateFreshness.from_payload(
                payload.get("freshness"),
                request_id=request_id,
            ),
            etag=_required_text(payload, "etag", request_id=request_id),
            items=tuple(
                RunningEstimateItem.from_payload(item, request_id=request_id)
                for item in raw_items
            ),
            final=_required_false(payload, "final", request_id=request_id),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "version": self.version,
            "schema_version": self.schema_version,
            "site_id": self.site_id,
            "site_timezone": self.site_timezone,
            "cluster_id": self.cluster_id,
            "scope": self.scope,
            "visibility_role": self.visibility_role,
            "slurm_user": self.slurm_user,
            "slurm_account": self.slurm_account,
            "as_of": self.as_of,
            "freshness": self.freshness.as_dict(),
            "etag": self.etag,
            "items": [item.as_dict() for item in self.items],
            "count": len(self.items),
            "final": self.final,
        }
