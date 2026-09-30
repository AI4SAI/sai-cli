"""Pure validation shared by independently authorized workspace directories."""
from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from .contracts import _nullable_nonempty_text, _required_text, _timestamp_text
from .errors import ConfigError, ContractError


_SITE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")


def workspace_page_query(*, site_id: str, limit: int, cursor: str | None,
                         workspace_key: str | None, clean_workspace: Callable[[object], str]) -> dict[str, str | int | None]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ConfigError("workspace page limit must be between 1 and 100")
    if not isinstance(site_id, str) or _SITE.fullmatch(site_id) is None or site_id.casefold() in {"default", "global"}:
        raise ConfigError("site must identify a configured site")
    if workspace_key is not None and cursor is not None:
        raise ConfigError("workspace key and cursor are mutually exclusive")
    for selector in (cursor, workspace_key):
        if selector is not None:
            clean_workspace(selector)
    return {"site_id": site_id, "limit": limit, "cursor": cursor, "workspace_key": workspace_key}


def parse_workspace_page(payload: object, *, schema: str, site_id: str, limit: int,
                         cursor: str | None, workspace_key: str | None,
                         clean_workspace: Callable[[object], str], request_id: str) -> dict[str, Any]:
    try:
        workspace_page_query(site_id=site_id, limit=limit, cursor=cursor,
                             workspace_key=workspace_key, clean_workspace=clean_workspace)
    except ConfigError as exc:
        raise ContractError(request_id=request_id) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != schema or payload.get("site_id") != site_id:
        raise ContractError(request_id=request_id)
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > limit:
        raise ContractError(request_id=request_id)
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ContractError(request_id=request_id)
        try:
            key = clean_workspace(item.get("workspace_key"))
        except ConfigError as exc:
            raise ContractError(request_id=request_id) from exc
        rows.append({"workspace_key": key,
                     "label": _required_text(item, "label", request_id=request_id, maximum=256),
                     "organization_label": _nullable_nonempty_text(item, "organization_label", request_id=request_id, maximum=256)})
    following = _nullable_nonempty_text(payload, "next_cursor", request_id=request_id, maximum=128)
    if following is not None:
        try:
            clean_workspace(following)
        except ConfigError as exc:
            raise ContractError(request_id=request_id) from exc
    more = payload.get("has_more")
    keys = [row["workspace_key"] for row in rows]
    if (type(more) is not bool or len(set(keys)) != len(keys) or cursor in keys
            or more != (following is not None) or (more and (not keys or following != keys[-1]))
            or (workspace_key is not None and (keys != [workspace_key] or more))):
        raise ContractError(request_id=request_id)
    queried_at = _timestamp_text(payload, "queried_at", request_id=request_id, nullable=False)
    if _UTC.fullmatch(queried_at) is None:
        raise ContractError(request_id=request_id)
    return {"schema_version": schema, "site_id": site_id, "queried_at": queried_at,
            "items": rows, "next_cursor": following, "has_more": more}
