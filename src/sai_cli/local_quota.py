"""Local path-to-project Lustre quota reads under the caller's Unix authority."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import os
import re
import time
from typing import Any, Mapping

from .errors import ConfigError, ContractError, ForbiddenError, NotFoundError, UnavailableError
from .native_process import read_native_output
from .native_values import local_options, native_environment, native_user
from .render import format_decimal
from .native_display import row


_FIELDS = ("--blocks", "--block-softlimit", "--block-hardlimit", "--block-grace",
           "--inodes", "--inode-softlimit", "--inode-hardlimit", "--inode-grace")
_COUNTERS = ("used_bytes", "block_soft_bytes", "block_hard_bytes", "used_inodes", "inode_soft", "inode_hard")
_GRACE = re.compile(r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)


def _invalid() -> ContractError:
    return ContractError("Lustre returned invalid quota data", code="native_response_invalid")


def _counter(value: str) -> tuple[int, bool]:
    token = value.strip()
    if re.fullmatch(r"[0-9]{1,20}\*?", token) is None:
        raise _invalid()
    number = int(token.rstrip("*"))
    if number > 2**64 - 1:
        raise _invalid()
    return number, token.endswith("*")


def _grace(value: str) -> dict[str, Any]:
    value = value.strip()
    lowered = value.lower()
    if lowered in {"-", "--"}:
        state, seconds = "inactive", None
    elif lowered == "expired":
        state, seconds = "expired", 0
    elif lowered == "notify":
        state, seconds = "notify", None
    elif re.fullmatch(r"[0-9]{1,20}", lowered):
        state, seconds = "remaining", int(lowered)
    else:
        match = _GRACE.fullmatch(lowered)
        if match is None or not any(match.groups()):
            raise _invalid()
        state = "remaining"
        seconds = sum(int(number or 0) * unit for number, unit in zip(match.groups(), (604800, 86400, 3600, 60, 1)))
    if seconds is not None and seconds > 2**64 - 1:
        raise _invalid()
    return {"raw": value, "state": state, "remaining_seconds": seconds}


def parse_quota_fields(raw: bytes) -> dict[str, Any]:
    """Use lfs's selected-field protocol, never split a human filesystem path."""
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise _invalid() from exc
    lines = text.splitlines()
    if len(lines) != 1:
        raise _invalid()
    values = lines[0].split("|")
    if len(values) != 9 or values[-1].strip():
        raise _invalid()
    counters = [_counter(values[index]) for index in (0, 1, 2, 4, 5, 6)]
    result = {name: str(number * (1024 if name.endswith("bytes") else 1))
              for name, (number, _) in zip(_COUNTERS, counters)}
    result.update(block_grace=_grace(values[3]), inode_grace=_grace(values[7]),
                  native_usage_markers={"space": counters[0][1], "inodes": counters[3][1]})
    return result


def _project_id(raw: bytes, *, path: str) -> int:
    # The filename tail may contain spaces, newlines or non-UTF-8 bytes.
    match = re.fullmatch(rb"[ \t]*([0-9]{1,10})[ \t]+([P-])[ \t]+([\s\S]*)\n", raw)
    if match is None or match[3] != os.fsencode(path):
        raise _invalid()
    value = int(match[1])
    if value == 0:
        raise NotFoundError("no Lustre project quota is assigned to this path", code="native_project_unassigned")
    if value >= 2**32 - 1:
        raise _invalid()
    return value


@dataclass(frozen=True)
class LocalQuota:
    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.values


def read_local_quota(args: argparse.Namespace, *, environ: Mapping[str, str]) -> LocalQuota:
    timeout = local_options(args, command="storage local-quota")
    actor = native_user()
    requested = args.path
    if not requested or "\x00" in requested:
        raise ConfigError("quota requires a nonempty filesystem path without NUL")
    try:
        path = os.path.realpath(requested, strict=True)
        before = os.stat(path)
    except FileNotFoundError as exc:
        raise NotFoundError("the quota path does not exist", code="native_path_not_found") from exc
    except PermissionError as exc:
        raise ForbiddenError("the current user cannot access the quota path", code="native_path_forbidden") from exc
    except OSError as exc:
        raise UnavailableError("the quota path cannot be resolved", code="native_path_unavailable") from exc
    env = native_environment(environ, filter_prefix="LFS_QUOTA_")
    env.update(LC_ALL="C", LANG="C")
    deadline = time.monotonic() + timeout

    def run(argv: list[str]) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UnavailableError("the native query timed out", code="native_query_timeout")
        return read_native_output(argv, environ=env, timeout=remaining, max_output_bytes=65536, reject_stderr=True)

    project = _project_id(run(["lfs", "project", "-d", "--", path]), path=path)
    quota = parse_quota_fields(run(["lfs", "quota", "-p", str(project), "-q", *_FIELDS,
                                   "--delimiter=|", "--", path]))
    try:
        after = os.stat(path)
    except OSError as exc:
        raise UnavailableError("the quota target changed during the read", code="native_target_changed") from exc
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise UnavailableError("the quota target changed during the read", code="native_target_changed")
    return LocalQuota({"schema_version": "native.quota/v1", "source": "lfs_quota", "authority": "native",
                      "coverage": "filesystem_project", "actor": {"user": actor, "uid": os.geteuid()},
                      "path": requested, "resolved_path": path, "host": os.uname().nodename,
                      "filesystem_device": {"major": os.major(before.st_dev), "minor": os.minor(before.st_dev)},
                      "native_project_id": project,
                      "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                      **quota})


def _size(value: str, *, limit: bool = False) -> str:
    number = int(value)
    if limit and number == 0:
        return "unlimited"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB")
    power = min((number.bit_length() - 1) // 10, len(units) - 1) if number else 0
    return f"{format_decimal(str(Decimal(number) / (1024 ** power)), 1, trim=True)} {units[power]}"


def _path_text(value: str) -> str:
    return "".join(f"\\x{ord(char):02x}" if ord(char) < 32 or 127 <= ord(char) <= 159 else
                   f"\\x{ord(char) - 0xdc00:02x}" if 0xdc80 <= ord(char) <= 0xdcff else char for char in value)


def render_local_quota(result: LocalQuota, *, width: int = 80) -> str:
    value = result.values
    files = lambda field: "unlimited" if int(value[field]) == 0 else f"{int(value[field]):,}"
    rows = [
        ["Space", _size(value["used_bytes"]) + ("*" if value["native_usage_markers"]["space"] else ""),
         _size(value["block_soft_bytes"], limit=True), _size(value["block_hard_bytes"], limit=True), value["block_grace"]["raw"]],
        ["Files", f"{int(value['used_inodes']):,}" + ("*" if value["native_usage_markers"]["inodes"] else ""),
         files("inode_soft"), files("inode_hard"), value["inode_grace"]["raw"]],
    ]
    headings = ["", "Used", "Quota", "Limit", "Grace"]
    widths = [max(len(headings[index]), *(len(cells[index]) for cells in rows)) for index in range(5)]
    if width >= 100:
        headings = ("used", "quota", "limit", "grace", "files", "quota", "limit", "grace")
        cells = [*rows[0][1:], *rows[1][1:]]
        widths = [max(8, len(heading), len(cell)) for heading, cell in zip(headings, cells, strict=True)]
        lines = [row(headings, widths), row(cells, widths)]
    else:
        lines = [row(headings, widths), "-" * (sum(widths) + 8), *(row(cells, widths) for cells in rows)]
    lines.insert(0, f"Disk quotas for project {value['native_project_id']}: {_path_text(value['path'])}")
    lines.append("Quota: soft limit; Limit: hard limit. Scope: filesystem project.")
    return "\n".join(lines) + "\n"
