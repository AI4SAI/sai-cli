"""Portal-owned job ownership for a same-origin Web navigation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from .contracts import _nullable_int, _required_text, _timestamp_text
from .errors import ContractError


SCHEMA_VERSION = "jobs.web-context/v1"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
_WORKSPACE = re.compile(r"(personal|org|project):[A-Za-z0-9][A-Za-z0-9._:-]*")
_JOB = re.compile(r"[0-9]+(?:_[0-9]+)?")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")
_SCOPES = {"personal_account": "personal", "org_account": "org", "project_account": "project"}


def _observation(payload: dict, *, request_id: str) -> tuple[str, str | None, int | None]:
    observed = _timestamp_text(payload, "observed_at", nullable=False, request_id=request_id)
    submitted = _timestamp_text(payload, "submit_time", nullable=True, request_id=request_id)
    restart = _nullable_int(payload, "restart_count", request_id=request_id)
    if any(value is not None and (len(value) > 64 or not _TIME.fullmatch(value)) for value in (observed, submitted)) or (
        restart is not None and restart > 65535
    ):
        raise ContractError(request_id=request_id)
    assert observed is not None
    return observed, submitted, restart


@dataclass(frozen=True)
class JobWebContext:
    workspace_key: str
    site_id: str
    cluster_id: str
    scope_type: str
    slurm_account_id: str
    job_id: str
    observed_at: str
    submit_time: str | None
    restart_count: int | None
    source_context: dict | None = None

    @classmethod
    def from_payload(cls, payload: object, *, request_id: str) -> JobWebContext:
        if not isinstance(payload, dict) or payload.get("schema_version") not in {SCHEMA_VERSION, "jobs.web-context/v2"}:
            raise ContractError(request_id=request_id)
        values = {key: _required_text(payload, key, maximum=128, request_id=request_id) for key in (
            "workspace_key", "site_id", "cluster_id", "scope_type", "slurm_account_id", "job_id",
        )}
        workspace = _WORKSPACE.fullmatch(values["workspace_key"])
        if (workspace is None or workspace.group(1) != _SCOPES.get(values["scope_type"])
                or any(_TOKEN.fullmatch(values[key]) is None for key in ("site_id", "cluster_id", "slurm_account_id"))
                or _JOB.fullmatch(values["job_id"]) is None):
            raise ContractError(request_id=request_id)
        observed, submitted, restart = _observation(payload, request_id=request_id)
        source = None
        if payload["schema_version"] == "jobs.web-context/v2":
            raw = payload.get("source_context")
            if not isinstance(raw, dict):
                raise ContractError(request_id=request_id)
            source = {key: _required_text(raw, key, maximum=128, request_id=request_id)
                      for key in ("scope_type", "slurm_account_id", "workspace_key")}
            if (source["scope_type"] != "org_account" or not _TOKEN.fullmatch(source["slurm_account_id"])
                    or not re.fullmatch(r"org:[A-Za-z0-9][A-Za-z0-9._:-]*", source["workspace_key"])
                    or values["scope_type"] != "project_account"):
                raise ContractError(request_id=request_id)
        return cls(**values, observed_at=observed, submit_time=submitted, restart_count=restart, source_context=source)

    def require_request_binding(self, *, site_id: str, cluster_id: str | None, scope: str,
                                account_id: str | None, job_id: str, request_id: str,
                                workspace_key: str | None = None) -> None:
        selected = self.source_context or {"scope_type": self.scope_type, "slurm_account_id": self.slurm_account_id, "workspace_key": self.workspace_key}
        if (self.site_id != site_id or (cluster_id is not None and self.cluster_id != cluster_id)
                or (self.source_context is not None and scope != "org_account")
                or self.job_id != job_id or (scope != "self" and selected["scope_type"] != scope)
                or (account_id is not None and selected["slurm_account_id"] != account_id)
                or (workspace_key is not None and selected["workspace_key"] != workspace_key)):
            raise ContractError(request_id=request_id)

    def as_dict(self) -> dict:
        result = asdict(self)
        if self.source_context is None:
            result.pop("source_context")
        return {"schema_version": "jobs.web-context/v2" if self.source_context else SCHEMA_VERSION, **result}

    def changed_since(self, *, submit_time: str | None, restart_count: int | None) -> bool:
        if self.submit_time is not None and submit_time is not None:
            current = datetime.fromisoformat(self.submit_time.replace("Z", "+00:00"))
            previous = datetime.fromisoformat(submit_time.replace("Z", "+00:00"))
            if current != previous:
                return True
        return self.restart_count is not None and restart_count is not None and self.restart_count != restart_count

    def web_url(self, base_url: str, *, observed_at: str, submit_time: str | None, restart_count: int | None) -> str:
        observed, submitted, restart = _observation({
            "observed_at": observed_at, "submit_time": submit_time, "restart_count": restart_count,
        }, request_id="job-web-context")
        context = {"workspace_key": self.workspace_key, "site_id": self.site_id, "cluster_id": self.cluster_id,
                   "job_id": self.job_id, "observed_at": observed, "submit_time": submitted, "restart_count": restart}
        origin = urlsplit(base_url)
        route = f"/portal/workspaces/{quote(self.workspace_key, safe='')}/{quote(self.site_id, safe='')}/jobs"
        fragment = route + "?" + urlencode({"job_context": json.dumps(context, separators=(",", ":"))})
        return urlunsplit((origin.scheme, origin.netloc, "/portal/", "", fragment))
