#!/usr/bin/env python3
"""Render a validated Portal projection as a deterministic Lua table."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_REVISION_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
_ROOT_KEYS = {
    "schema_version",
    "revision",
    "generated_at",
    "expires_at",
    "gpu_policy",
}


class ProjectionError(ValueError):
    pass


def _token(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise ProjectionError(f"{field} must be a canonical token")
    return value


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProjectionError(f"{field} must be an integer >= {minimum}")
    return value


def validate_projection(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _ROOT_KEYS:
        raise ProjectionError("projection fields do not match schema version 2")
    if raw["schema_version"] != 2:
        raise ProjectionError("schema_version must be 2")
    revision = raw["revision"]
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise ProjectionError("revision must be a canonical revision token")
    generated_at = _integer(raw["generated_at"], field="generated_at", minimum=1)
    expires_at = _integer(raw["expires_at"], field="expires_at", minimum=generated_at + 1)

    gpu_policy = raw["gpu_policy"]
    if not isinstance(gpu_policy, dict) or set(gpu_policy) != {"per_node_multiple", "exempt_qos"}:
        raise ProjectionError("gpu_policy fields do not match schema version 2")
    multiple = _integer(gpu_policy["per_node_multiple"], field="gpu_policy.per_node_multiple", minimum=1)
    exempt_raw = gpu_policy["exempt_qos"]
    if not isinstance(exempt_raw, list):
        raise ProjectionError("gpu_policy.exempt_qos must be an array")
    exempt_qos = sorted({_token(item, field="gpu_policy.exempt_qos item") for item in exempt_raw})

    return {
        "schema_version": 2,
        "revision": revision,
        "generated_at": generated_at,
        "expires_at": expires_at,
        "gpu_per_node_multiple": multiple,
        "gpu_multiple_exempt_qos": exempt_qos,
    }


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_lua(projection: dict[str, Any]) -> str:
    lines = [
        "return {",
        "    schema_version = 2,",
        f"    revision = {_quoted(projection['revision'])},",
        f"    generated_at = {projection['generated_at']},",
        f"    expires_at = {projection['expires_at']},",
        f"    gpu_per_node_multiple = {projection['gpu_per_node_multiple']},",
        "    gpu_multiple_exempt_qos = {",
    ]
    lines.extend(f"        [{_quoted(qos)}] = true," for qos in projection["gpu_multiple_exempt_qos"])
    lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        projection = validate_projection(raw)
        _atomic_write(args.output, render_lua(projection))
    except (OSError, json.JSONDecodeError, ProjectionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
