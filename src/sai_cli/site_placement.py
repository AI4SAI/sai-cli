"""Operator-recorded asset locations joined to one authorized allocation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .contracts import _nullable_nonempty_text, _nullable_sha256_text, _required_int, _required_text, _timestamp_text
from .errors import ContractError
from .site_jobs import SiteJobAllocationResult


_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")


def _object(value: object, request_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(request_id=request_id)
    return value


def _reference(row: dict[str, Any], field: str, request_id: str, *, nullable: bool = False) -> str | None:
    value = (_nullable_nonempty_text(row, field, request_id=request_id, maximum=128) if nullable
             else _required_text(row, field, request_id=request_id, maximum=128))
    if value is not None and _REF.fullmatch(value) is None:
        raise ContractError(request_id=request_id)
    return value


def _instant(row: dict[str, Any], field: str, request_id: str) -> str:
    value = _timestamp_text(row, field, request_id=request_id, nullable=False)
    if value is None or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value) is None:
        raise ContractError(request_id=request_id)
    return value


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


@dataclass(frozen=True)
class SitePlacementInventory:
    revision: str
    generation: int
    published_at: str
    expires_at: str


@dataclass(frozen=True)
class SiteRegisteredRack:
    ref: str
    label: str
    u_start: int
    u_height: int


@dataclass(frozen=True)
class SiteAssetRegistration:
    asset_ref: str
    incarnation_ref: str
    placement_ref: str | None
    label: str
    verified_at: str
    valid_until: str
    rack: SiteRegisteredRack | None

    @classmethod
    def from_payload(cls, value: object, *, request_id: str) -> "SiteAssetRegistration":
        row = _object(value, request_id)
        placement = _reference(row, "placement_ref", request_id, nullable=True)
        if "rack" not in row or (row["rack"] is None) != (placement is None):
            raise ContractError(request_id=request_id)
        rack = None
        if row["rack"] is not None:
            raw = _object(row["rack"], request_id)
            start = _required_int(raw, "u_start", request_id=request_id)
            height = _required_int(raw, "u_height", request_id=request_id)
            if not 1 <= start <= 100 or not 1 <= height <= 100 or start + height - 1 > 100:
                raise ContractError(request_id=request_id)
            rack = SiteRegisteredRack(
                _reference(raw, "ref", request_id),
                _required_text(raw, "label", request_id=request_id, maximum=128), start, height,
            )
        return cls(
            _reference(row, "asset_ref", request_id), _reference(row, "incarnation_ref", request_id), placement,
            _required_text(row, "label", request_id=request_id, maximum=128),
            _instant(row, "verified_at", request_id), _instant(row, "valid_until", request_id), rack,
        )


@dataclass(frozen=True)
class SitePlacementNode:
    name: str
    status: str
    registration: SiteAssetRegistration | None


@dataclass(frozen=True)
class SiteJobPlacementResult:
    allocation: SiteJobAllocationResult
    inventory: SitePlacementInventory | None
    nodes: tuple[SitePlacementNode, ...]

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> "SiteJobPlacementResult":
        row = _object(payload, request_id)
        if row.get("schema_version") != ("jobs.placement/v2" if isinstance(row.get("allocation"), dict) and row["allocation"].get("schema_version") == "jobs.allocation/v3" else "jobs.placement/v1") or row.get("coverage") != "allocated_nodes_only":
            raise ContractError(request_id=request_id)
        allocation = SiteJobAllocationResult.from_payload(row.get("allocation"), request_id=request_id)
        raw_nodes = row.get("nodes")
        if "inventory" not in row or not isinstance(raw_nodes, list) or len(raw_nodes) > 4096:
            raise ContractError(request_id=request_id)
        if not allocation.nodes:
            if row["inventory"] is not None or raw_nodes:
                raise ContractError(request_id=request_id)
            return cls(allocation, None, ())
        raw_inventory = _object(row["inventory"], request_id)
        revision = _nullable_sha256_text(raw_inventory, "revision", request_id=request_id)
        generation = _required_int(raw_inventory, "generation", request_id=request_id)
        if revision is None or not 1 <= generation <= 9007199254740991:
            raise ContractError(request_id=request_id)
        inventory = SitePlacementInventory(revision, generation, _instant(raw_inventory, "published_at", request_id),
                                           _instant(raw_inventory, "expires_at", request_id))
        observed = _date(_instant({"observed_at": allocation.freshness.observed_at}, "observed_at", request_id))
        published, expires = _date(inventory.published_at), _date(inventory.expires_at)
        if not published <= observed < expires:
            raise ContractError(request_id=request_id)
        nodes = []
        racks: dict[str, tuple[str, list[tuple[int, int]]]] = {}
        references: dict[str, set[str]] = {key: set() for key in ("asset_ref", "incarnation_ref", "placement_ref")}
        for value in raw_nodes:
            node = _object(value, request_id)
            name = _required_text(node, "name", request_id=request_id, maximum=128)
            status = _required_text(node, "status", request_id=request_id, maximum=32)
            if "registration" not in node or status not in {"recorded", "unmapped", "expired"}:
                raise ContractError(request_id=request_id)
            registration = None
            if status == "recorded":
                registration = SiteAssetRegistration.from_payload(node["registration"], request_id=request_id)
                for key, seen in references.items():
                    reference = getattr(registration, key)
                    if reference is not None:
                        if reference in seen:
                            raise ContractError(request_id=request_id)
                        seen.add(reference)
                verified, valid_until = _date(registration.verified_at), _date(registration.valid_until)
                if not verified <= published or not verified <= observed < valid_until <= expires:
                    raise ContractError(request_id=request_id)
                rack = registration.rack
                if rack is not None:
                    label, ranges = racks.setdefault(rack.ref, (rack.label, []))
                    end = rack.u_start + rack.u_height - 1
                    if label != rack.label or any(rack.u_start <= stop and start <= end for start, stop in ranges):
                        raise ContractError(request_id=request_id)
                    ranges.append((rack.u_start, end))
            elif node["registration"] is not None:
                raise ContractError(request_id=request_id)
            nodes.append(SitePlacementNode(name, status, registration))
        if [node.name for node in nodes] != [node.name for node in allocation.nodes]:
            raise ContractError(request_id=request_id)
        return cls(allocation, inventory, tuple(nodes))

    def require_request_binding(self, **context: Any) -> None:
        self.allocation.require_request_binding(**context)

    def require_current(self, *, request_id: str) -> None:
        if self.inventory is None:
            return
        now = datetime.now(timezone.utc)
        expiries = [self.inventory.expires_at]
        expiries.extend(node.registration.valid_until for node in self.nodes if node.registration is not None)
        if any(now >= _date(value) for value in expiries):
            raise ContractError("registered locations expired before receipt; read again", request_id=request_id)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "jobs.placement/v2" if self.allocation.subaccounts else "jobs.placement/v1", "allocation": self.allocation.as_dict(),
                "inventory": None if self.inventory is None else asdict(self.inventory),
                "coverage": "allocated_nodes_only", "nodes": [asdict(node) for node in self.nodes]}
