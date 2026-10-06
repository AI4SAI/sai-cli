"""Allowlisted, version-bound text pages from an authorized task output."""
from dataclasses import dataclass
import re

from .errors import ConfigError, ContractError
from .managed_runs import ManagedReadResult, _file_context, _integer, _boolean, _relative_filename, _token, terminal_log
from .messages import Messages


ARTIFACT = re.compile(r"artifact-[0-9a-f]{40}")
CURSOR = re.compile(r"([0-9a-f]{64}):(0|[1-9][0-9]{0,18})")
VERSION = re.compile(r"[0-9a-f]{64}")
MAX_OFFSET = 2**63 - 1


def content_cursor(value: object) -> tuple[str | None, int]:
    if value is None:
        return None, 0
    match = CURSOR.fullmatch(value) if isinstance(value, str) else None
    if match is None or int(match[2]) > MAX_OFFSET:
        raise ConfigError("artifact content cursor is invalid")
    return match[1], int(match[2])


@dataclass(frozen=True)
class ManagedRunArtifactContent(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str, run_ref: str,
                     artifact_ref: str, cursor: str | None, request_id: str) -> "ManagedRunArtifactContent":
        data, result = _file_context(payload, "compute.run-artifact-content/v1", workspace_key, site_id, run_ref, request_id)
        expected_version, offset = content_cursor(cursor)
        reference = _token(data, "artifact_ref", request_id, pattern=ARTIFACT)
        version = _token(data, "version", request_id, nullable=True, pattern=VERSION)
        current = _token(data, "cursor", request_id, nullable=True, pattern=CURSOR)
        following = _token(data, "next_cursor", request_id, nullable=True, pattern=CURSOR)
        path = _relative_filename(data.get("relative_path"), request_id)
        status, content = data.get("status"), data.get("content")
        if (reference != artifact_ref or current != cursor or not isinstance(status, str)
                or status not in {"available", "missing", "unsupported", "changed"}
                or not isinstance(content, str) or len(content) > 65536):
            raise ContractError(request_id=request_id)
        try:
            size = len(content.encode("utf-8"))
        except UnicodeError as exc:
            raise ContractError(request_id=request_id) from exc
        count = _integer(data, "bytes_read", request_id, maximum=65536)
        start = _integer(data, "offset", request_id, maximum=MAX_OFFSET)
        end = _integer(data, "next_offset", request_id, maximum=MAX_OFFSET)
        complete = _boolean(data, "complete", request_id)
        metadata = {}
        for key, maximum in (("size_bytes", MAX_OFFSET), ("modified_at_ns", 2**127 - 1)):
            if key not in data:
                raise ContractError(request_id=request_id)
            metadata[key] = None if data[key] is None else _integer(data, key, request_id, maximum=maximum)
        if size > 65536 or start != offset or (status == "missing") != (version is None):
            raise ContractError(request_id=request_id)
        if any((value is None) != (status == "missing") for value in metadata.values()):
            raise ContractError(request_id=request_id)
        if status == "available":
            if (size != count or "\0" in content or end != offset + count or end > metadata["size_bytes"]
                    or complete != (end == metadata["size_bytes"]) or not complete and count == 0
                    or expected_version is not None and version != expected_version
                    or following != (None if complete else f"{version}:{end}")):
                raise ContractError(request_id=request_id)
        elif content or count or end != start or complete or following is not None:
            raise ContractError(request_id=request_id)
        return cls({**result, "artifact_ref": reference, "relative_path": path, "status": status,
                    "content": content, "version": version, "cursor": current, "next_cursor": following,
                    "offset": start, "next_offset": end, "bytes_read": count, "complete": complete, **metadata})


def render_artifact_content(result: ManagedRunArtifactContent, language: str = "en-US") -> str:
    data, t = result.values, Messages(language)
    lines = [terminal_log(data["relative_path"]), data["observed_at"], ""]
    if data["status"] == "available":
        lines.extend((terminal_log(data["content"]) or t("content_empty"),
                      t("content_end" if data["complete"] else "content_more")))
    else:
        lines.append(t("content_" + data["status"]))
    return "\n".join(lines)
