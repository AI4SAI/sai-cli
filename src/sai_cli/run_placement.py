"""Run-bound placement wrapping the existing authorized job observation."""
from dataclasses import dataclass
from datetime import datetime
import re

from .errors import ContractError
from .managed_runs import ManagedReadResult, _context, _integer, _object, _time, _token
from .render import render_site_placement
from .site_placement import SiteJobPlacementResult


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


@dataclass(frozen=True)
class ManagedRunPlacement(ManagedReadResult):
    placement: SiteJobPlacementResult

    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str,
                     run_ref: str, request_id: str) -> "ManagedRunPlacement":
        data, values = _context(payload, "compute.run-placement/v1", workspace_key, site_id, request_id)
        if _token(data, "run_ref", request_id) != run_ref or "execution" not in data:
            raise ContractError(request_id=request_id)
        placement = SiteJobPlacementResult.from_payload(data.get("placement"), request_id=request_id)
        allocation = placement.allocation
        if (allocation.site_id != site_id or allocation.freshness.source != "scontrol"
                or allocation.scope_type != "project_account" or allocation.slurm_user is None or allocation.slurm_account is None
                or allocation.job.values["array_task_id"] is not None):
            raise ContractError(request_id=request_id)
        execution = None
        if allocation.allocation_status == "not_allocated":
            if data["execution"] is not None:
                raise ContractError(request_id=request_id)
        else:
            native = _object(data["execution"], request_id)
            execution = {"sluid": _token(native, "sluid", request_id, pattern=re.compile(r"s[0-9A-HJKMNP-TV-Z]{13}")),
                         "submit_time": _time(native, "submit_time", request_id),
                         "start_time": _time(native, "start_time", request_id),
                         "restart_count": _integer(native, "restart_count", request_id, maximum=9007199254740991),
                         "resize_time": _time(native, "resize_time", request_id, nullable=True)}
            if (allocation.restart_count != execution["restart_count"] or any(
                allocation.job.values[field] is None or _instant(allocation.job.values[field]) != _instant(execution[field])
                for field in ("submit_time", "start_time")
            )):
                raise ContractError(request_id=request_id)
        return cls({**values, "run_ref": run_ref, "queried_at": _time(data, "queried_at", request_id),
                    "execution": execution}, placement)

    def as_dict(self) -> dict:
        return {**super().as_dict(), "placement": self.placement.as_dict()}


def render_run_placement(result: ManagedRunPlacement) -> str:
    data = result.values
    lines = [f"Run: {data['run_ref']} · Project: {data['workspace_key']} · Site: {data['site_id']}",
             f"Queried: {data['queried_at']}"]
    if data["execution"] is not None:
        lines.append(f"Runtime SLUID: {data['execution']['sluid']}")
    return "\n".join(lines) + "\n" + render_site_placement(result.placement)
