"""Authorized directory metadata from the existing Portal file-access owner."""
from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
from unicodedata import combining, east_asian_width

from .errors import ConfigError, ContractError
from .managed_runs import terminal_log
from .render import _line, follow_up_command


_CURSOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,35}~[0-9a-f]{64}")
_SITE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_ACTIONS = ("browse", "reference", "work_directory", "edit", "terminal", "byok", "sai_model", "compute")
_REASONS = {"read_only", "account_permission_required", "needs_project_compute_permission", "workspace_site_unavailable"}
_REFERENCES = ("workspace_ref", "workspace_mount_ref", "scope_ref", "account_workspace_key")
_LABELS = ("label", "path_label", "scope_label")


def directory_query(*, site_id: str, limit: int, cursor: str | None) -> dict[str, str | int | None]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ConfigError("directory page limit must be between 1 and 100")
    if not isinstance(site_id, str) or _SITE.fullmatch(site_id) is None or site_id.casefold() in {"default", "global"}:
        raise ConfigError("site must identify a configured site")
    if cursor is not None and (not isinstance(cursor, str) or _CURSOR.fullmatch(cursor) is None):
        raise ConfigError("directory cursor must come from the previous page")
    return {"site_id": site_id, "limit": limit, "cursor": cursor}


@dataclass(frozen=True)
class FileWorkspaces:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, limit: int,
                     cursor: str | None, request_id: str) -> FileWorkspaces:
        try:
            directory_query(site_id=site_id, limit=limit, cursor=cursor)
        except ConfigError as exc:
            raise ContractError(request_id=request_id) from exc
        if (not isinstance(payload, dict) or payload.get("schema_version") != "file-workspace-discovery/v1"
                or payload.get("site_id") != site_id):
            raise ContractError(request_id=request_id)
        raw = payload.get("items")
        if not isinstance(raw, list) or len(raw) > limit or "next_cursor" not in payload:
            raise ContractError(request_id=request_id)
        following = payload["next_cursor"]
        if following is not None and (not isinstance(following, str) or _CURSOR.fullmatch(following) is None or following == cursor):
            raise ContractError(request_id=request_id)
        items = []
        for item in raw:
            if not isinstance(item, dict):
                raise ContractError(request_id=request_id)
            row = {}
            for key in (*_REFERENCES, *_LABELS, "path"):
                value = item.get(key)
                if not isinstance(value, str) or not value or key in _REFERENCES and len(value) > 256:
                    raise ContractError(request_id=request_id)
                row[key] = value
            if len(row["path"]) < 2 or not row["path"].startswith("/") or "\0" in row["path"]:
                raise ContractError(request_id=request_id)
            if (not isinstance(item.get("kind"), str) or item["kind"] not in {"home", "org_share", "org_user_dir", "project_root"}
                    or not isinstance(item.get("role"), str) or item["role"] not in {"read", "write"}):
                raise ContractError(request_id=request_id)
            actions = item.get("actions")
            if not isinstance(actions, dict):
                raise ContractError(request_id=request_id)
            clean = {}
            for key in _ACTIONS:
                action = actions.get(key)
                if (not isinstance(action, dict) or type(action.get("allowed")) is not bool or "reason" not in action
                        or action["reason"] is not None and (not isinstance(action["reason"], str) or action["reason"] not in _REASONS)
                        or action["allowed"] != (action["reason"] is None)):
                    raise ContractError(request_id=request_id)
                clean[key] = {"allowed": action["allowed"], "reason": action["reason"]}
            items.append({**row, "kind": item["kind"], "role": item["role"], "actions": clean})
        if len({row["workspace_ref"] for row in items}) != len(items):
            raise ContractError(request_id=request_id)
        return cls({"schema_version": "file-workspace-discovery/v1", "site_id": site_id,
                    "items": items, "next_cursor": following})

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


def render_directories(result: FileWorkspaces, *, args: Namespace | None = None, limit: int = 50) -> str:
    def visible(value: str) -> str:
        return terminal_log(value).replace("\n", r"\n").replace("\t", r"\t")

    def width(value: str) -> int:
        return sum(0 if combining(char) else 2 if east_asian_width(char) in {"W", "F"} else 1 for char in value)

    def name(value: str) -> str:
        value = visible(value)
        if width(value) <= 40:
            return value
        count, clipped = 0, []
        for char in value:
            if count + width(char) > 37:
                break
            clipped.append(char)
            count += width(char)
        return "".join(clipped) + "..."

    rows = [("Name", "Access", "Path"), *((name(row["label"]),
             "Read/write" if row["role"] == "write" else "Read", visible(row["path"]))
            for row in result.values["items"])]
    name_width = max(width(row[0]) for row in rows)
    lines = [_line(row, [name_width-width(row[0])+len(row[0]), 10, 0]) for row in rows]
    if not result.values["items"]:
        lines.append("No directories on this page.")
    if result.values["next_cursor"] is not None:
        command = follow_up_command(args, "storage", "directories", "--site", result.values["site_id"],
            "--limit", str(limit), "--cursor", result.values["next_cursor"])
        lines.append("Next page: " + visible(command))
    return "\n".join(lines) + "\n"
