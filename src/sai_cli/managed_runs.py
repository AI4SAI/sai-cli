"""Allowlisted managed task receipts and bounded, separately authorized file pages."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from .contracts import _required_text, _timestamp_text
from .errors import ConfigError, ContractError


_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")
_STATUS = {"accepted", "queued", "running", "completed", "failed", "canceled", "canceling", "needs_attention"}
_RUN_TIMES = ("accepted_at", "queued_at", "started_at", "finished_at", "last_observed_at")


def clean_run_ref(value: object) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise ConfigError("run reference is invalid")
    return value


def clean_tasks_workspace(value: object) -> str:
    if (not isinstance(value, str) or len(value) > 128 or not value.startswith("project:")
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value[8:]) is None):
        raise ConfigError("tasks workspace must be project:<id>")
    return value


def _object(value: object, request_id: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(request_id=request_id)
    return value


def _text(data: dict, key: str, request_id: str, *, nullable: bool = False, maximum: int = 128) -> str | None:
    if key not in data:
        raise ContractError(request_id=request_id)
    if data[key] is None and nullable:
        return None
    return _required_text(data, key, maximum=maximum, request_id=request_id)


def _time(data: dict, key: str, request_id: str, *, nullable: bool = False) -> str | None:
    value = _timestamp_text(data, key, request_id=request_id, nullable=nullable)
    if value is not None and (len(value) > 64 or _UTC.fullmatch(value) is None):
        raise ContractError(request_id=request_id)
    return value


def _integer(data: dict, key: str, request_id: str, *, maximum: int | None = None, minimum: int = 0) -> int:
    value = data.get(key)
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ContractError(request_id=request_id)
    return value


def _boolean(data: dict, key: str, request_id: str) -> bool:
    if type(data.get(key)) is not bool:
        raise ContractError(request_id=request_id)
    return data[key]


def _token(data: dict, key: str, request_id: str, *, nullable: bool = False, pattern=_REF) -> str | None:
    value = _text(data, key, request_id, nullable=nullable)
    if value is not None and pattern.fullmatch(value) is None:
        raise ContractError(request_id=request_id)
    return value


def _context(payload: object, schema: str, workspace_key: str, site_id: str, request_id: str) -> tuple[dict, dict]:
    data = _object(payload, request_id)
    if (data.get("schema_version") != schema or data.get("workspace_key") != workspace_key
            or data.get("site_id") != site_id):
        raise ContractError(request_id=request_id)
    try:
        clean_tasks_workspace(workspace_key)
    except ConfigError as exc:
        raise ContractError(request_id=request_id) from exc
    if not isinstance(site_id, str) or len(site_id) > 64 or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", site_id) is None:
        raise ContractError(request_id=request_id)
    return data, {"schema_version": schema, "workspace_key": workspace_key, "site_id": site_id}


def _receipt_context(payload: object, schema: str, workspace_key: str, site_id: str, request_id: str) -> tuple[dict, dict]:
    data, result = _context(payload, schema, workspace_key, site_id, request_id)
    if data.get("source") != "portal_run_receipts":
        raise ContractError(request_id=request_id)
    return data, {**result, "source": "portal_run_receipts", "queried_at": _time(data, "queried_at", request_id)}


def _run(payload: object, request_id: str) -> dict:
    data = _object(payload, request_id)
    result = {"run_ref": _token(data, "run_ref", request_id), "cluster_id": _text(data, "cluster_id", request_id, maximum=64)}
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]*", result["cluster_id"]) is None:
        raise ContractError(request_id=request_id)
    if "title" not in data:
        raise ContractError(request_id=request_id)
    title = data["title"]
    if title is not None and (not isinstance(title, str) or not 1 <= len(title) <= 512
                             or any(char == "/" or ord(char) < 32 or ord(char) == 127 for char in title)):
        raise ContractError(request_id=request_id)
    status = _text(data, "status", request_id)
    if status not in _STATUS:
        raise ContractError(request_id=request_id)
    code = _text(data, "error_code", request_id, nullable=True, maximum=64)
    if code is not None and re.fullmatch(r"[A-Za-z0-9_.:-]+", code) is None:
        raise ContractError(request_id=request_id)
    result.update(title=title, status=status, state_revision=_integer(data, "state_revision", request_id, minimum=1),
                  scheduler_ref=_token(data, "scheduler_ref", request_id, nullable=True),
                  scheduler_state=_text(data, "scheduler_state", request_id, nullable=True, maximum=64), error_code=code)
    result.update({key: _time(data, key, request_id, nullable=key != "accepted_at") for key in _RUN_TIMES})
    return result


def _file_context(payload: object, schema: str, workspace_key: str, site_id: str, run_ref: str, request_id: str) -> tuple[dict, dict]:
    data, result = _context(payload, schema, workspace_key, site_id, request_id)
    if _token(data, "run_ref", request_id) != run_ref:
        raise ContractError(request_id=request_id)
    freshness = _object(data.get("freshness"), request_id)
    if freshness.get("source") != "site-agent":
        raise ContractError(request_id=request_id)
    result.update(run_ref=run_ref, observed_at=_time(data, "observed_at", request_id),
                  freshness={"source": "site-agent", "queried_at": _time(freshness, "queried_at", request_id)})
    if result["observed_at"] != result["freshness"]["queried_at"]:
        raise ContractError(request_id=request_id)
    return data, result


@dataclass(frozen=True)
class ManagedReadResult:
    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


@dataclass(frozen=True)
class ManagedRunWorkspaces(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, limit: int,
                     cursor: str | None, request_id: str) -> ManagedRunWorkspaces:
        data = _object(payload, request_id)
        if (data.get("schema_version") != "compute.workspaces/v1" or data.get("site_id") != site_id
                or not isinstance(site_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", site_id) is None):
            raise ContractError(request_id=request_id)
        items = data.get("items")
        if not isinstance(items, list) or len(items) > min(limit, 100):
            raise ContractError(request_id=request_id)
        rows = []
        for raw in items:
            item = _object(raw, request_id)
            try:
                workspace = clean_tasks_workspace(item.get("workspace_key"))
            except ConfigError as exc:
                raise ContractError(request_id=request_id) from exc
            rows.append({"workspace_key": workspace,
                         "label": _text(item, "label", request_id, maximum=256),
                         "organization_label": _text(item, "organization_label", request_id, nullable=True, maximum=256)})
        following = _text(data, "next_cursor", request_id, nullable=True)
        if following is not None:
            try:
                clean_tasks_workspace(following)
            except ConfigError as exc:
                raise ContractError(request_id=request_id) from exc
        more = _boolean(data, "has_more", request_id)
        keys = [row["workspace_key"] for row in rows]
        if (len(set(keys)) != len(keys) or cursor in keys or more != (following is not None)
                or (more and (not keys or following != keys[-1]))):
            raise ContractError(request_id=request_id)
        return cls({"schema_version": "compute.workspaces/v1", "site_id": site_id,
                    "queried_at": _time(data, "queried_at", request_id), "items": rows,
                    "next_cursor": following, "has_more": more})


@dataclass(frozen=True)
class ManagedRunList(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, limit: int,
                     cursor: str | None, request_id: str) -> ManagedRunList:
        data, result = _receipt_context(payload, "compute.runs/v1", workspace_key, site_id, request_id)
        items = data.get("items")
        if not isinstance(items, list) or len(items) > min(limit, 100):
            raise ContractError(request_id=request_id)
        rows = [_run(item, request_id) for item in items]
        following = _token(data, "next_cursor", request_id, nullable=True)
        more = _boolean(data, "has_more", request_id)
        if (len({row["run_ref"] for row in rows}) != len(rows) or any(row["run_ref"] == cursor for row in rows)
                or more != (following is not None)
                or (more and (not rows or following != rows[-1]["run_ref"] or following == cursor))):
            raise ContractError(request_id=request_id)
        return cls({**result, "items": rows, "next_cursor": following, "has_more": more})


@dataclass(frozen=True)
class ManagedRunDetail(ManagedReadResult):
    def web_url(self, base_url: str, *, artifact_page: ManagedRunArtifacts | None = None,
                artifact_ref: str | None = None, cost: bool = False) -> str:
        origin = urlsplit(base_url)
        route = (f"/portal/workspaces/{quote(self.values['workspace_key'], safe='')}/"
                 f"{quote(self.values['site_id'], safe='')}/runs")
        query = {"run_ref": self.values["run"]["run_ref"]}
        if type(cost) is not bool or (cost and (artifact_page is not None or artifact_ref is not None)):
            raise ConfigError("cost continuation cannot include a file selection")
        if cost:
            query["view"] = "cost"
        if artifact_page is not None or artifact_ref is not None:
            if not isinstance(artifact_page, ManagedRunArtifacts) or not isinstance(artifact_ref, str):
                raise ConfigError("file continuation requires a current file page and reference")
            artifact_page.require_selection(self, artifact_ref)
            query.update(view="files", artifact_ref=artifact_ref)
            if artifact_page.request_cursor is not None:
                query["artifact_cursor"] = artifact_page.request_cursor
        fragment = route + "?" + urlencode(query)
        return urlunsplit((origin.scheme, origin.netloc, "/portal/", "", fragment))

    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, run_ref: str, request_id: str) -> ManagedRunDetail:
        data, result = _receipt_context(payload, "compute.run/v1", workspace_key, site_id, request_id)
        run = _run(data.get("run"), request_id)
        if run["run_ref"] != run_ref:
            raise ContractError(request_id=request_id)
        return cls({**result, "run": run})


@dataclass(frozen=True)
class ManagedRunLogs(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, run_ref: str,
                     stream: str, cursor: str | None, max_bytes: int, request_id: str) -> ManagedRunLogs:
        data, result = _file_context(payload, "compute-run-log.v1", workspace_key, site_id, run_ref, request_id)
        current = _text(data, "cursor", request_id)
        following = _text(data, "next_cursor", request_id)
        pattern = re.compile(rf"log-{stream}-(0|[1-9][0-9]{{0,18}})")
        content = data.get("content")
        try:
            content_bytes = len(content.encode("utf-8")) if isinstance(content, str) else None
        except UnicodeEncodeError as exc:
            raise ContractError(request_id=request_id) from exc
        if (data.get("stream") != stream or current != (cursor or f"log-{stream}-0") or pattern.fullmatch(current) is None
                or (following is not None and pattern.fullmatch(following) is None)
                or content_bytes is None or content_bytes > min(max_bytes, 65536)):
            raise ContractError(request_id=request_id)
        available, complete, truncated = (_boolean(data, key, request_id) for key in ("available", "complete", "truncated"))
        offset, next_offset = int(current.rsplit("-", 1)[1]), int(following.rsplit("-", 1)[1])
        if (truncated != (available and not complete) or (not available and (content or complete))
                or not 0 <= offset <= next_offset <= 2**63 - 1 or (truncated and next_offset == offset)):
            raise ContractError(request_id=request_id)
        if next_offset - offset != content_bytes:
            raise ContractError(request_id=request_id)
        return cls({**result, "stream": stream, "available": available, "content": content,
                    "cursor": current, "next_cursor": following, "truncated": truncated, "complete": complete})


@dataclass(frozen=True)
class ManagedRunArtifacts(ManagedReadResult):
    request_cursor: str | None = None

    def require_selection(self, detail: ManagedRunDetail, artifact_ref: str) -> None:
        if (not isinstance(detail, ManagedRunDetail) or not isinstance(artifact_ref, str)
                or _REF.fullmatch(artifact_ref) is None
                or self.values["run_ref"] != detail.values["run"]["run_ref"]
                or any(self.values[key] != detail.values[key] for key in ("workspace_key", "site_id"))
                or self.values["cursor"] != (self.request_cursor or "0")
                or (self.request_cursor is not None and (not isinstance(self.request_cursor, str)
                    or re.fullmatch(r"0|[1-9][0-9]{0,8}", self.request_cursor) is None))
                or not any(item["artifact_ref"] == artifact_ref for item in self.values["items"])):
            raise ConfigError("file continuation must select an item in the current task file page")
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, run_ref: str,
                     cursor: str | None, limit: int, request_id: str) -> ManagedRunArtifacts:
        data, result = _file_context(payload, "compute-run-artifacts.v1", workspace_key, site_id, run_ref, request_id)
        current = _text(data, "cursor", request_id)
        following = _text(data, "next_cursor", request_id, nullable=True)
        complete = _boolean(data, "complete", request_id)
        items = data.get("items")
        pattern = re.compile(r"0|[1-9][0-9]{0,8}")
        if (current != (cursor or "0") or pattern.fullmatch(current) is None or complete != (following is None)
                or (following is not None and pattern.fullmatch(following) is None)
                or not isinstance(items, list) or len(items) > min(limit, 100)):
            raise ContractError(request_id=request_id)
        rows = []
        for item in items:
            row = _object(item, request_id)
            path = _relative_filename(row.get("relative_path"), request_id)
            if row.get("kind") != "file":
                raise ContractError(request_id=request_id)
            rows.append({"artifact_ref": _token(row, "artifact_ref", request_id),
                         "display_name": _relative_filename(row.get("display_name"), request_id), "relative_path": path,
                         "kind": "file", "size_bytes": _integer(row, "size_bytes", request_id, maximum=2**63-1),
                         "modified_at_ns": _integer(row, "modified_at_ns", request_id)})
        if (len({row["artifact_ref"] for row in rows}) != len(rows) or len({row["relative_path"] for row in rows}) != len(rows)
                or (not complete and (not rows or int(following) != int(current) + len(rows)))):
            raise ContractError(request_id=request_id)
        return cls({**result, "cursor": current, "next_cursor": following, "complete": complete, "items": rows}, cursor)


def terminal_log(content: str) -> str:
    return "".join(f"\\x{ord(char):02x}" if (ord(char) < 32 and char not in "\n\t") or 127 <= ord(char) <= 159 else char for char in content)


def _relative_filename(value: object, request_id: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 1024
            or any(ord(char) < 32 or ord(char) == 127 or char == "\\" for char in value)):
        raise ContractError(request_id=request_id)
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {".", ".."} for part in value.split("/")):
        raise ContractError(request_id=request_id)
    return value


def render_managed_runs(result: ManagedReadResult) -> str:
    data = result.values
    if isinstance(result, ManagedRunWorkspaces):
        lines = [f"Readable projects · Site: {data['site_id']} · queried {data['queried_at']}"]
        lines.extend(f"{row['workspace_key']}  {row['label']}" + (
            f" · {row['organization_label']}" if row['organization_label'] is not None else ""
        ) for row in data["items"])
        lines.append(f"Next cursor: {data['next_cursor'] or 'None'}")
        return "\n".join(lines) + "\n"
    lines = [f"Project: {data['workspace_key']} · Site: {data['site_id']}"]
    if isinstance(result, (ManagedRunList, ManagedRunDetail)):
        lines.append(f"Managed run records · queried {data['queried_at']} (not live queue state)")
        for run in data["items"] if isinstance(result, ManagedRunList) else [data["run"]]:
            lines.append(f"{run['run_ref']}  {run['status']}  {terminal_log(run['title']) if run['title'] is not None else 'Untitled'}")
            lines.append(f"Scheduler ID: {run['scheduler_ref'] or 'Not assigned'} · observed {run['last_observed_at'] or 'Unknown'}")
        if isinstance(result, ManagedRunList):
            lines.append(f"Next cursor: {data['next_cursor'] or 'None'}")
        else:
            run = data["run"]
            lines.extend(f"{key}: {run[key] if run[key] is not None else 'Unknown'}" for key in
                         ("state_revision", "cluster_id", "scheduler_state", *_RUN_TIMES[:-1], "error_code"))
    else:
        lines.append(f"Run: {data['run_ref']} · observed {data['observed_at']}")
        if isinstance(result, ManagedRunLogs):
            state = "Not available" if not data["available"] else "Complete" if data["complete"] else "More pages"
            lines.append(f"{data['stream']} · {state} · cursor {data['cursor']}")
            lines.append(terminal_log(data["content"]) if data["available"] else "Log is not available yet.")
        else:
            lines.extend(f"{terminal_log(row['display_name'])}  {row['size_bytes']} bytes  modified(ns) {row['modified_at_ns']}" for row in data["items"])
            if not data["items"]:
                lines.append("No output files in this page.")
        lines.append(f"Next cursor: {data['next_cursor'] or 'None'}")
    return "\n".join(lines) + "\n"
