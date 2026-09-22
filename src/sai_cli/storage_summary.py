"""Allowlisted central quota observations, distinct from live filesystem reads."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .contracts import _nullable_nonempty_text, _required_text, _timestamp_text
from .errors import ConfigError, ContractError


SCHEMA_VERSION = "storage.quota-summary/v1"
_STATES = {"ready", "pending", "failed", "drift", "unavailable"}
_WORKSPACE = re.compile(r"(?:personal|org|project):[A-Za-z0-9][A-Za-z0-9_-]*")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")
_CAPACITIES = (
    "target_total_tib", "effective_total_tib", "used_tib", "remaining_tib",
    "observed_soft_limit_tib", "observed_hard_limit_tib",
)
_COUNTS = ("used_inodes", "inode_soft_limit", "inode_hard_limit")
_TIMES = ("observed_at", "quota_updated_at")


def clean_workspace_key(value: object) -> str:
    if not isinstance(value, str) or len(value) > 128 or _WORKSPACE.fullmatch(value) is None:
        raise ConfigError("workspace must be personal:<id>, org:<id>, or project:<id>")
    return value


@dataclass(frozen=True)
class StorageQuotaSummary:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, request_id: str) -> StorageQuotaSummary:
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise ContractError(request_id=request_id)
        values: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
        for key in ("workspace_key", "site_id", "state", "source"):
            values[key] = _required_text(payload, key, request_id=request_id, maximum=128)
        if (values["workspace_key"] != workspace_key or values["site_id"] != site_id
                or values["state"] not in _STATES or values["source"] != "portal_quota_observation"):
            raise ContractError(request_id=request_id)
        values["mount_id"] = _nullable_nonempty_text(payload, "mount_id", request_id=request_id, maximum=128)
        if values["mount_id"] is not None and any(ord(char) <= 32 for char in values["mount_id"]):
            raise ContractError(request_id=request_id)
        for key in _CAPACITIES:
            value = _nullable_nonempty_text(payload, key, request_id=request_id, maximum=64)
            unsigned = value[1:] if value and value.startswith("-") and key == "remaining_tib" else value
            if unsigned is not None and _DECIMAL.fullmatch(unsigned) is None:
                raise ContractError(request_id=request_id)
            values[key] = value
        for key in _COUNTS:
            if key not in payload:
                raise ContractError(request_id=request_id)
            value = payload[key]
            if value is not None and (type(value) is not int or not 0 <= value <= 9007199254740991):
                raise ContractError(request_id=request_id)
            values[key] = value
        for key in _TIMES:
            value = _timestamp_text(payload, key, request_id=request_id, nullable=True)
            if value is not None and _TIME.fullmatch(value) is None:
                raise ContractError(request_id=request_id)
            values[key] = value
        return cls(values)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)
