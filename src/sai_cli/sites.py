"""Published site names for explicit selection, with no routing or access grants."""
import re

from .errors import ConfigError, ContractError
from .managed_runs import ManagedReadResult, _boolean, _integer, _object, _text, _time
from .render import _line


_SITE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


def site_directory_query(*, limit: int, cursor: str | None) -> dict[str, str | int | None]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ConfigError("site page limit must be between 1 and 100")
    if cursor is not None and (not isinstance(cursor, str) or _SITE.fullmatch(cursor) is None
                               or cursor.casefold() in {"default", "global"}):
        raise ConfigError("site cursor must be a site ID from the previous page")
    return {"limit": limit, "cursor": cursor}


class SiteDirectory(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, limit: int, cursor: str | None, request_id: str):
        data = _object(payload, request_id)
        if data.get("schema_version") != "site.directory/v1" or data.get("source") != "portal_published_sites":
            raise ContractError(request_id=request_id)
        raw = data.get("items")
        if not isinstance(raw, list) or len(raw) > limit:
            raise ContractError(request_id=request_id)
        items = []
        for value in raw:
            row = _object(value, request_id)
            site = _text(row, "site_id", request_id, maximum=64)
            if _SITE.fullmatch(site) is None or site.casefold() in {"default", "global"}:
                raise ContractError(request_id=request_id)
            items.append({"site_id": site, "display_name": _text(row, "display_name", request_id, maximum=256)})
        keys = [row["site_id"] for row in items]
        count = _integer(data, "count", request_id, maximum=limit)
        more = _boolean(data, "has_more", request_id)
        following = _text(data, "next_cursor", request_id, nullable=True, maximum=64)
        if (count != len(items) or keys != sorted(set(keys))
                or cursor is not None and any(key <= cursor for key in keys)
                or more != (following is not None) or more and (not keys or following != keys[-1])):
            raise ContractError(request_id=request_id)
        return cls({"schema_version": "site.directory/v1", "source": "portal_published_sites",
                    "queried_at": _time(data, "queried_at", request_id), "items": items, "count": count,
                    "has_more": more, "next_cursor": following})


def render_sites(result: SiteDirectory) -> str:
    rows = [(row["site_id"], row["display_name"]) for row in result.values["items"]]
    if not rows:
        return "No published sites on this page.\n"
    widths = [max(len("Site"), *(len(row[0]) for row in rows)), 0]
    lines = [_line(("Site", "Name"), widths), *(_line(row, widths) for row in rows)]
    if result.values["has_more"]:
        lines.append(f"Next: sai sites --cursor {result.values['next_cursor']} --format table")
    return "\n".join(lines) + "\n"
