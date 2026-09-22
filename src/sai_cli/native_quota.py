"""Native quota observations shared by terminal, web and Agent consumers."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .contracts import _required_text, _timestamp_text
from .errors import ContractError


SCHEMA_VERSION = "storage.native-quota/v1"
KINDS = {"home", "organization_shared", "directory", "project"}
COUNTERS = ("used_bytes", "used_inodes", "block_soft_bytes", "block_hard_bytes", "inode_soft", "inode_hard")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,22})")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")


@dataclass(frozen=True)
class NativeQuotaResult:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, request_id: str) -> NativeQuotaResult:
        expected = {
            "schema_version": SCHEMA_VERSION, "workspace_key": workspace_key,
            "site_id": site_id, "source": "lustre_quota",
            "coverage": "authorized_quota_subjects",
        }
        if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in expected.items()):
            raise ContractError(request_id=request_id)
        values: dict[str, Any] = dict(expected)
        values["as_of"] = _timestamp_text(payload, "as_of", request_id=request_id, nullable=False)
        if _TIME.fullmatch(values["as_of"]) is None:
            raise ContractError(request_id=request_id)
        etag = _required_text(payload, "etag", request_id=request_id, maximum=64)
        if re.fullmatch(r"[0-9a-f]{64}", etag) is None:
            raise ContractError(request_id=request_id)
        values["etag"] = etag
        rows = payload.get("items")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
            raise ContractError(request_id=request_id)
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ContractError(request_id=request_id)
            item = {}
            for field in ("quota_ref", "allocation_ref", "mount_id", "kind", "label"):
                item[field] = _required_text(row, field, request_id=request_id, maximum=256 if field == "label" else 128)
            if item["kind"] not in KINDS or any(
                _REFERENCE.fullmatch(item[field]) is None for field in ("quota_ref", "allocation_ref", "mount_id")
            ) or item["quota_ref"] in seen:
                raise ContractError(request_id=request_id)
            seen.add(item["quota_ref"])
            item["observed_at"] = _timestamp_text(row, "observed_at", request_id=request_id, nullable=False)
            if _TIME.fullmatch(item["observed_at"]) is None:
                raise ContractError(request_id=request_id)
            for field in COUNTERS:
                value = _required_text(row, field, request_id=request_id, maximum=23)
                if _INTEGER.fullmatch(value) is None or int(value) > (2**64 - 1) * (1024 if field.endswith("bytes") else 1):
                    raise ContractError(request_id=request_id)
                item[field] = value
            items.append(item)
        values["items"] = items
        return cls(values)

    def as_dict(self) -> dict[str, Any]:
        return {**self.values, "items": [dict(row) for row in self.values["items"]]}
