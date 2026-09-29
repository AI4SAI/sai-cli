"""Allowlisted published resource catalog; no availability or price calculation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from .errors import ConfigError, ContractError


SCHEMA_VERSION = "site.resource-catalog/v1"
_UNSAFE_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_PRICE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return value


def _text(value: object, *, maximum: int = 4096, empty: bool = False) -> str:
    if (not isinstance(value, str) or len(value) > maximum
            or (not empty and not value) or _UNSAFE_TEXT.search(value)):
        raise ValueError("invalid text")
    return value


def _token(value: object) -> str:
    value = _text(value, maximum=128)
    if any(ord(character) <= 32 for character in value):
        raise ValueError("invalid token")
    return value


def _nullable_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _items(value: object, *, maximum: int = 128) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("invalid list")
    return value


def _count(value: object) -> int | None:
    if value is not None and (type(value) is not int or not 0 <= value <= 9007199254740991):
        raise ValueError("invalid count")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("invalid boolean")
    return value


def _price(value: object) -> dict[str, str]:
    row = _object(value)
    amount = _text(row["unit_price"], maximum=64)
    if row["currency"] != "CNY" or _PRICE.fullmatch(amount) is None:
        raise ValueError("invalid price")
    return {
        "currency": "CNY",
        "unit_price": amount,
        "unit_name": _text(row["unit_name"]),
        "display": _text(row["display"]),
    }


def _compute(value: object) -> dict[str, Any]:
    row = _object(value)
    kind = row["resource_kind"]
    if kind is not None and kind not in ("cpu", "gpu"):
        raise ValueError("invalid resource kind")
    return {
        "name": _token(row["name"]),
        "title": _text(row["title"]),
        "resource_kind": kind,
        "summary": _text(row["summary"], empty=True),
        "scenarios": [_text(item, empty=True) for item in _items(row["scenarios"])],
        "node_count": _count(row["node_count"]),
        "cpu_cores_per_node": _count(row["cpu_cores_per_node"]),
        "cpu_model": _nullable_text(row["cpu_model"]),
        "gpu_count": _count(row["gpu_count"]),
        "gpu_model": _nullable_text(row["gpu_model"]),
        "supported_qos": [_token(item) for item in _items(row["supported_qos"])],
        "pricing": None if row["pricing"] is None else _price(row["pricing"]),
    }


def _storage(value: object) -> dict[str, Any]:
    row = _object(value)
    if row["scope_kind"] not in ("personal_home", "organization_project"):
        raise ValueError("invalid storage scope")
    hardware = []
    for item in _items(row["hardware"]):
        fact = _object(item)
        hardware.append({"label": _text(fact["label"]), "value": _text(fact["value"])})
    return {
        "name": _text(row["name"]),
        "description": _text(row["description"], empty=True),
        "filesystem_type": _token(row["filesystem_type"]),
        "physical_filesystem_key": _token(row["physical_filesystem_key"]),
        "scope_kind": row["scope_kind"],
        "scope_label": _text(row["scope_label"]),
        "hardware": hardware,
        "self_service_available": _boolean(row["self_service_available"]),
        "metered_settlement_enabled": _boolean(row["metered_settlement_enabled"]),
        "package_pricing": _price(row["package_pricing"]),
        "usage_pricing": _price(row["usage_pricing"]),
    }


@dataclass(frozen=True)
class ResourceCatalog:
    values: dict[str, Any]

    def preparation_url(self, base_url: str, partition_ref: str) -> str:
        if (not isinstance(partition_ref, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,63}", partition_ref) is None
                or sum(row["name"] == partition_ref for row in self.values["compute"]) != 1):
            raise ConfigError("select one published compute partition with a valid reference")
        origin = urlsplit(base_url)
        query = urlencode({"site_id": self.values["site_id"], "partition_ref": partition_ref})
        return urlunsplit((origin.scheme, origin.netloc, "/portal/", "", "/portal/resources/prepare?" + query))

    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, request_id: str) -> ResourceCatalog:
        try:
            row = _object(payload)
            if row["schema_version"] != SCHEMA_VERSION or row["site_id"] != site_id:
                raise ValueError("catalog binding mismatch")
            return cls({
                "schema_version": SCHEMA_VERSION,
                "site_id": _token(row["site_id"]),
                "site_label": _text(row["site_label"]),
                "compute": [_compute(item) for item in _items(row["compute"], maximum=512)],
                "storage": [_storage(item) for item in _items(row["storage"], maximum=512)],
            })
        except (KeyError, TypeError, ValueError):
            raise ContractError("the resource catalog response is invalid", request_id=request_id) from None

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)
