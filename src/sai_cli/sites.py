"""Published site names and explicit-site connection metadata, without access grants."""
from dataclasses import replace
from argparse import Namespace
import re
from urllib.parse import urlsplit

from .config import Settings, _site_read_origin
from .errors import ConfigError, ContractError, UnavailableError
from .managed_runs import ManagedReadResult, _boolean, _integer, _object, _text, _time
from .render import _line, follow_up_command


_SITE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


class SiteConnection(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, request_id: str):
        from .client import clean_token

        data = _object(payload, request_id)
        if data.get("schema_version") != "site.connection/v1" or data.get("site_id") != site_id:
            raise ContractError(request_id=request_id)
        cluster = _text(data, "cluster_id", request_id, maximum=64)
        origin = _text(data, "site_read_base_url", request_id, nullable=True, maximum=2048)
        try:
            if clean_token(cluster, field="cluster", required=True, maximum=64) != cluster:
                raise ValueError("invalid cluster")
            origin = _site_read_origin(origin, managed=False)
        except (ConfigError, ValueError) as exc:
            raise ContractError("The site connection metadata is invalid.", request_id=request_id) from exc
        return cls({"schema_version": "site.connection/v1", "site_id": site_id,
                    "cluster_id": cluster, "site_read_base_url": origin})


def resolve_site_settings(settings: Settings, connection: SiteConnection, *, gateway: bool) -> Settings:
    """Fill missing connection facts from the selected site's canonical metadata."""
    value = connection.values
    if settings.cluster_id is not None and settings.cluster_id != value["cluster_id"]:
        raise ConfigError("The configured cluster does not match the selected site.")
    origin = settings.site_read_base_url
    if gateway and origin is None:
        origin = value["site_read_base_url"]
        if origin is None:
            raise UnavailableError("The selected site has no published native-read endpoint.")
        if urlsplit(settings.base_url).scheme == "https" and urlsplit(origin).scheme != "https":
            raise ContractError("The site connection metadata would downgrade HTTPS.")
    return replace(settings, cluster_id=value["cluster_id"], site_read_base_url=origin)


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


def render_sites(result: SiteDirectory, *, args: Namespace | None = None) -> str:
    rows = [(row["site_id"], row["display_name"]) for row in result.values["items"]]
    if not rows:
        return "No published sites on this page.\n"
    widths = [max(len("Site"), *(len(row[0]) for row in rows)), 0]
    lines = [_line(("Site", "Name"), widths), *(_line(row, widths) for row in rows)]
    if result.values["has_more"]:
        from .managed_runs import terminal_log
        lines.append("Next: " + terminal_log(follow_up_command(args, "sites", "--cursor", result.values['next_cursor'],
            "--limit", str(getattr(args, "limit", 50)), "--format", "table")))
    return "\n".join(lines) + "\n"
