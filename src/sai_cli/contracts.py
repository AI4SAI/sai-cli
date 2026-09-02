"""Strict allowlisted jobs/v1 and gross running-estimate/v2 contracts."""
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
    "job_generation_key",
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
    "currency",
    "pricing_revision",
    "estimate_status",
    "uncertainty",
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
    "nodes",
)

_DECIMAL_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_MONEY_RE = re.compile(r"^[0-9]+\.[0-9]{8}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_SCOPES = {"self", "personal_account", "org_account", "project_account"}
_ESTIMATE_STATUSES = {"estimated", "not_started", "unavailable"}
_RESOURCE_TYPES = {"gpu", "cpu"}


def _object(value: object, *, request_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(request_id=request_id)
    return value


def _has_unsafe_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _required_text(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    maximum: int = 4096,
) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or _has_unsafe_control(value)
    ):
        raise ContractError(request_id=request_id)
    return value


def _nullable_text(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    maximum: int = 4096,
) -> str | None:
    if key not in payload:
        raise ContractError(request_id=request_id)
    value = payload[key]
    if value is not None and (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or _has_unsafe_control(value)
    ):
        raise ContractError(request_id=request_id)
    return value


def _nullable_int(payload: dict[str, Any], key: str, *, request_id: str) -> int | None:
    if key not in payload:
        raise ContractError(request_id=request_id)
    value = payload[key]
    if value is not None and (type(value) is not int or value < 0):
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
    if value:
        raise ContractError(request_id=request_id)
    return value


def _literal(
    payload: dict[str, Any],
    key: str,
    expected: str,
    *,
    request_id: str,
) -> str:
    value = _required_text(payload, key, request_id=request_id, maximum=128)
    if value != expected:
        raise ContractError(request_id=request_id)
    return value


def _timestamp(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    nullable: bool,
) -> str | None:
    value = _nullable_text(payload, key, request_id=request_id, maximum=64)
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


def _decimal(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
    nullable: bool,
    money: bool = False,
) -> str | None:
    value = _nullable_text(payload, key, request_id=request_id, maximum=128)
    if value is None:
        if nullable:
            return None
        raise ContractError(request_id=request_id)
    if (_MONEY_RE if money else _DECIMAL_RE).fullmatch(value) is None:
        raise ContractError(request_id=request_id)
    return value


def _nullable_sha256(
    payload: dict[str, Any],
    key: str,
    *,
    request_id: str,
) -> str | None:
    value = _nullable_text(payload, key, request_id=request_id, maximum=64)
    if value is not None and _SHA256_RE.fullmatch(value) is None:
        raise ContractError(request_id=request_id)
    return value


def _timezone(payload: dict[str, Any], *, request_id: str) -> str:
    value = _required_text(payload, "site_timezone", request_id=request_id, maximum=64)
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ContractError(request_id=request_id) from exc
    return value


def _machine_codes(
    payload: dict[str, Any],
    *,
    request_id: str,
) -> tuple[str, ...]:
    raw = payload.get("uncertainty")
    if not isinstance(raw, list) or len(raw) > 32:
        raise ContractError(request_id=request_id)
    values = tuple(raw)
    if (
        any(not isinstance(value, str) or _MACHINE_CODE_RE.fullmatch(value) is None for value in values)
        or values != tuple(sorted(set(values)))
    ):
        raise ContractError(request_id=request_id)
    return values


@dataclass(frozen=True)
class ReadSubject:
    slurm_user: str | None
    slurm_account: str | None

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> ReadSubject:
        value = _object(payload, request_id=request_id)
        subject = cls(
            slurm_user=_nullable_text(
                value,
                "slurm_user",
                request_id=request_id,
                maximum=128,
            ),
            slurm_account=_nullable_text(
                value,
                "slurm_account",
                request_id=request_id,
                maximum=128,
            ),
        )
        if subject.slurm_user is None and subject.slurm_account is None:
            raise ContractError(request_id=request_id)
        return subject

    def validate_scope(self, scope_type: str, *, request_id: str) -> None:
        if scope_type == "self":
            if self.slurm_user is None or self.slurm_account is not None:
                raise ContractError(request_id=request_id)
        elif self.slurm_account is None:
            raise ContractError(request_id=request_id)

    def as_dict(self) -> dict[str, str | None]:
        return {
            "slurm_user": self.slurm_user,
            "slurm_account": self.slurm_account,
        }


@dataclass(frozen=True)
class ReadFreshness:
    source: str
    observed_at: str
    ttl_seconds: int
    age_seconds: int
    stale: bool

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> ReadFreshness:
        value = _object(payload, request_id=request_id)
        observed_at = _timestamp(
            value,
            "observed_at",
            request_id=request_id,
            nullable=False,
        )
        return cls(
            source=_required_text(value, "source", request_id=request_id, maximum=64),
            observed_at=observed_at or "",
            ttl_seconds=_required_int(value, "ttl_seconds", request_id=request_id),
            age_seconds=_required_int(value, "age_seconds", request_id=request_id),
            stale=_required_bool(value, "stale", request_id=request_id),
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
class JobItem:
    values: dict[str, str | int | None]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> JobItem:
        value = _object(payload, request_id=request_id)
        values: dict[str, str | int | None] = {
            "job_id": _required_text(value, "job_id", request_id=request_id, maximum=128),
            "array_task_id": _nullable_text(value, "array_task_id", request_id=request_id, maximum=128),
            "name": _nullable_text(value, "name", request_id=request_id),
            "slurm_user": _required_text(value, "slurm_user", request_id=request_id, maximum=128),
            "slurm_account": _required_text(value, "slurm_account", request_id=request_id, maximum=128),
            "state": _required_text(value, "state", request_id=request_id, maximum=32),
            "priority": _nullable_int(value, "priority", request_id=request_id),
            "submit_time": _timestamp(value, "submit_time", request_id=request_id, nullable=True),
            "start_time": _timestamp(value, "start_time", request_id=request_id, nullable=True),
            "elapsed_seconds": _nullable_int(value, "elapsed_seconds", request_id=request_id),
            "run_wait_seconds": _nullable_int(value, "run_wait_seconds", request_id=request_id),
            "partition": _nullable_text(value, "partition", request_id=request_id, maximum=128),
            "qos": _nullable_text(value, "qos", request_id=request_id, maximum=128),
            "nodes": _nullable_int(value, "nodes", request_id=request_id),
            "slots": _nullable_int(value, "slots", request_id=request_id),
            "gpus_per_node": _nullable_int(value, "gpus_per_node", request_id=request_id),
            "mem_per_unit": _nullable_text(value, "mem_per_unit", request_id=request_id, maximum=128),
            "reason_or_nodelist": _nullable_text(value, "reason_or_nodelist", request_id=request_id),
        }
        return cls(values=values)

    def as_dict(self) -> dict[str, str | int | None]:
        return {key: self.values[key] for key in JOB_ITEM_FIELDS}


@dataclass(frozen=True)
class JobResult:
    schema_version: str
    site_id: str
    cluster_id: str
    scope_type: str
    subject: ReadSubject
    freshness: ReadFreshness
    etag: str
    has_more: bool
    items: tuple[JobItem, ...]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> JobResult:
        value = _object(payload, request_id=request_id)
        raw_items = value.get("items")
        if not isinstance(raw_items, list):
            raise ContractError(request_id=request_id)
        scope_type = _required_text(value, "scope_type", request_id=request_id, maximum=32)
        if scope_type not in _SCOPES:
            raise ContractError(request_id=request_id)
        subject = ReadSubject.from_payload(value.get("subject"), request_id=request_id)
        subject.validate_scope(scope_type, request_id=request_id)
        items = tuple(JobItem.from_payload(item, request_id=request_id) for item in raw_items)
        for item in items:
            if subject.slurm_user is not None and item.values["slurm_user"] != subject.slurm_user:
                raise ContractError(request_id=request_id)
            if subject.slurm_account is not None and item.values["slurm_account"] != subject.slurm_account:
                raise ContractError(request_id=request_id)
        return cls(
            schema_version=_literal(value, "schema_version", "jobs/v1", request_id=request_id),
            site_id=_required_text(value, "site_id", request_id=request_id, maximum=64),
            cluster_id=_required_text(value, "cluster_id", request_id=request_id, maximum=64),
            scope_type=scope_type,
            subject=subject,
            freshness=ReadFreshness.from_payload(value.get("freshness"), request_id=request_id),
            etag=_required_text(value, "etag", request_id=request_id, maximum=128),
            has_more=_required_bool(value, "has_more", request_id=request_id),
            items=items,
        )

    def require_request_binding(
        self,
        *,
        site_id: object,
        cluster_id: object,
        scope_type: object,
        request_id: str,
    ) -> None:
        if (self.site_id, self.cluster_id, self.scope_type) != (
            site_id,
            cluster_id,
            scope_type,
        ):
            raise ContractError(request_id=request_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "site_id": self.site_id,
            "cluster_id": self.cluster_id,
            "scope_type": self.scope_type,
            "subject": self.subject.as_dict(),
            "freshness": self.freshness.as_dict(),
            "etag": self.etag,
            "has_more": self.has_more,
            "items": [item.as_dict() for item in self.items],
        }


def _alloc_tres(payload: object, *, request_id: str) -> dict[str, str | int]:
    value = _object(payload, request_id=request_id)
    return {
        "gpu": _required_int(value, "gpu", request_id=request_id),
        "cpu": _required_int(value, "cpu", request_id=request_id),
        "mem_mb": _decimal(value, "mem_mb", request_id=request_id, nullable=False) or "",
        "nodes": _required_int(value, "nodes", request_id=request_id),
    }


def _resources(payload: object, *, request_id: str) -> dict[str, Any]:
    value = _object(payload, request_id=request_id)
    if "alloc_tres" not in value:
        raise ContractError(request_id=request_id)
    raw_alloc_tres = value.get("alloc_tres")
    resource_type = _nullable_text(value, "resource_type", request_id=request_id, maximum=32)
    if resource_type is not None and resource_type not in _RESOURCE_TYPES:
        raise ContractError(request_id=request_id)
    return {
        "partition": _nullable_text(value, "partition", request_id=request_id, maximum=128),
        "qos": _nullable_text(value, "qos", request_id=request_id, maximum=128),
        "nodes": _nullable_int(value, "nodes", request_id=request_id),
        "alloc_tres": None if raw_alloc_tres is None else _alloc_tres(raw_alloc_tres, request_id=request_id),
        "resource_type": resource_type,
        "resource_count": _nullable_int(value, "resource_count", request_id=request_id),
        "usage_quantity": _decimal(value, "usage_quantity", request_id=request_id, nullable=True),
    }


@dataclass(frozen=True)
class RunningEstimateItem:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> RunningEstimateItem:
        value = _object(payload, request_id=request_id)
        status = _required_text(value, "estimate_status", request_id=request_id, maximum=32)
        if status not in _ESTIMATE_STATUSES:
            raise ContractError(request_id=request_id)
        resources = _resources(value.get("resources"), request_id=request_id)
        values: dict[str, Any] = {
            "job_generation_key": _required_text(
                value,
                "job_generation_key",
                request_id=request_id,
                maximum=160,
            ),
            "job_id_raw": _required_text(value, "job_id_raw", request_id=request_id, maximum=128),
            "slurm_job_db_index": _nullable_int(value, "slurm_job_db_index", request_id=request_id),
            "slurm_user": _required_text(value, "slurm_user", request_id=request_id, maximum=128),
            "slurm_account": _required_text(value, "slurm_account", request_id=request_id, maximum=128),
            "state": _required_text(value, "state", request_id=request_id, maximum=32),
            "submit_time": _timestamp(value, "submit_time", request_id=request_id, nullable=False),
            "start_time": _timestamp(value, "start_time", request_id=request_id, nullable=True),
            "elapsed_seconds": _nullable_int(value, "elapsed_seconds", request_id=request_id),
            "resources": resources,
            "gross_cny": _decimal(value, "gross_cny", request_id=request_id, nullable=True, money=True),
            "currency": _literal(value, "currency", "CNY", request_id=request_id),
            "pricing_revision": _nullable_sha256(value, "pricing_revision", request_id=request_id),
            "estimate_status": status,
            "uncertainty": list(_machine_codes(value, request_id=request_id)),
        }
        priced = (
            values["job_generation_key"],
            values["gross_cny"],
            values["pricing_revision"],
            resources["resource_type"],
            resources["resource_count"],
            resources["usage_quantity"],
        )
        if status == "estimated" and (
            any(item is None for item in priced)
            or values["start_time"] is None
            or values["elapsed_seconds"] is None
            or values["uncertainty"]
        ):
            raise ContractError(request_id=request_id)
        if status == "not_started" and (
            any(
                item is not None
                for item in (
                    values["gross_cny"],
                    values["pricing_revision"],
                    resources["resource_type"],
                    resources["resource_count"],
                    resources["usage_quantity"],
                )
            )
            or values["uncertainty"]
        ):
            raise ContractError(request_id=request_id)
        if status == "unavailable" and (
            values["gross_cny"] is not None
            or values["pricing_revision"] is not None
            or not values["uncertainty"]
        ):
            raise ContractError(request_id=request_id)
        return cls(values=values)

    def as_dict(self) -> dict[str, Any]:
        return {key: self.values[key] for key in RUNNING_ESTIMATE_ITEM_FIELDS}


@dataclass(frozen=True)
class RunningEstimateResult:
    schema_version: str
    site_id: str
    cluster_id: str
    scope_type: str
    subject: ReadSubject
    site_timezone: str
    freshness: ReadFreshness
    etag: str
    final: bool
    items: tuple[RunningEstimateItem, ...]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> RunningEstimateResult:
        value = _object(payload, request_id=request_id)
        raw_items = value.get("items")
        if not isinstance(raw_items, list):
            raise ContractError(request_id=request_id)
        scope_type = _required_text(value, "scope_type", request_id=request_id, maximum=32)
        if scope_type not in _SCOPES:
            raise ContractError(request_id=request_id)
        subject = ReadSubject.from_payload(value.get("subject"), request_id=request_id)
        subject.validate_scope(scope_type, request_id=request_id)
        items = tuple(
            RunningEstimateItem.from_payload(item, request_id=request_id)
            for item in raw_items
        )
        for item in items:
            if subject.slurm_user is not None and item.values["slurm_user"] != subject.slurm_user:
                raise ContractError(request_id=request_id)
            if subject.slurm_account is not None and item.values["slurm_account"] != subject.slurm_account:
                raise ContractError(request_id=request_id)
        return cls(
            schema_version=_literal(
                value,
                "schema_version",
                "billing.running-estimate/v2",
                request_id=request_id,
            ),
            site_id=_required_text(value, "site_id", request_id=request_id, maximum=64),
            cluster_id=_required_text(value, "cluster_id", request_id=request_id, maximum=64),
            scope_type=scope_type,
            subject=subject,
            site_timezone=_timezone(value, request_id=request_id),
            freshness=ReadFreshness.from_payload(value.get("freshness"), request_id=request_id),
            etag=_required_text(value, "etag", request_id=request_id, maximum=128),
            final=_required_false(value, "final", request_id=request_id),
            items=items,
        )

    def require_request_binding(
        self,
        *,
        site_id: object,
        cluster_id: object,
        scope_type: object,
        request_id: str,
    ) -> None:
        if (self.site_id, self.cluster_id, self.scope_type) != (
            site_id,
            cluster_id,
            scope_type,
        ):
            raise ContractError(request_id=request_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "site_id": self.site_id,
            "cluster_id": self.cluster_id,
            "scope_type": self.scope_type,
            "subject": self.subject.as_dict(),
            "site_timezone": self.site_timezone,
            "freshness": self.freshness.as_dict(),
            "etag": self.etag,
            "final": self.final,
            "items": [item.as_dict() for item in self.items],
        }


__all__ = [
    "JOB_ITEM_FIELDS",
    "RUNNING_ESTIMATE_ALLOC_TRES_FIELDS",
    "RUNNING_ESTIMATE_ITEM_FIELDS",
    "RUNNING_ESTIMATE_RESOURCE_FIELDS",
    "JobItem",
    "JobResult",
    "ReadFreshness",
    "ReadSubject",
    "RunningEstimateItem",
    "RunningEstimateResult",
]
