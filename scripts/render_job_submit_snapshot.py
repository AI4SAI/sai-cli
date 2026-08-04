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
    "personal_accounts",
    "org_accounts",
    "project_accounts",
    "home_aliases",
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


def _mapping(value: object, *, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProjectionError(f"{field} must be an object")
    output: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _token(raw_key, field=f"{field} key")
        output[key] = _token(raw_value, field=f"{field}[{key}]")
    return output


def validate_projection(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _ROOT_KEYS:
        raise ProjectionError("projection fields do not match schema version 1")
    if raw["schema_version"] != 1:
        raise ProjectionError("schema_version must be 1")
    revision = raw["revision"]
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise ProjectionError("revision must be a canonical revision token")
    generated_at = _integer(raw["generated_at"], field="generated_at", minimum=1)
    expires_at = _integer(raw["expires_at"], field="expires_at", minimum=generated_at + 1)

    gpu_policy = raw["gpu_policy"]
    if not isinstance(gpu_policy, dict) or set(gpu_policy) != {"per_node_multiple", "exempt_qos"}:
        raise ProjectionError("gpu_policy fields do not match schema version 1")
    multiple = _integer(gpu_policy["per_node_multiple"], field="gpu_policy.per_node_multiple", minimum=1)
    exempt_raw = gpu_policy["exempt_qos"]
    if not isinstance(exempt_raw, list):
        raise ProjectionError("gpu_policy.exempt_qos must be an array")
    exempt_qos = sorted({_token(item, field="gpu_policy.exempt_qos item") for item in exempt_raw})

    personal = _mapping(raw["personal_accounts"], field="personal_accounts")
    orgs = _mapping(raw["org_accounts"], field="org_accounts")

    projects_raw = raw["project_accounts"]
    if not isinstance(projects_raw, dict):
        raise ProjectionError("project_accounts must be an object")
    projects: dict[str, str] = {}
    for raw_key, raw_value in projects_raw.items():
        if not isinstance(raw_key, str) or raw_key.count("/") != 1:
            raise ProjectionError("project_accounts keys must be org/project")
        org, project = raw_key.split("/", 1)
        key = f"{_token(org, field='project org')}/{_token(project, field='project directory')}"
        if org not in orgs:
            raise ProjectionError(f"project_accounts[{key}] references an unknown org")
        projects[key] = _token(raw_value, field=f"project_accounts[{key}]")

    aliases_raw = raw["home_aliases"]
    if not isinstance(aliases_raw, dict):
        raise ProjectionError("home_aliases must be an object")
    aliases: dict[str, str] = {}
    for raw_key, raw_org in aliases_raw.items():
        if not isinstance(raw_key, str) or raw_key.count("/") != 1:
            raise ProjectionError("home_aliases keys must be user/workdir_org")
        user, alias = raw_key.split("/", 1)
        key = f"{_token(user, field='alias user')}/{_token(alias, field='alias name')}"
        org = _token(raw_org, field=f"home_aliases[{key}]")
        if not alias.startswith("workdir_") or org not in orgs:
            raise ProjectionError(f"home_aliases[{key}] is not a provisioned org alias")
        aliases[key] = org

    return {
        "schema_version": 1,
        "revision": revision,
        "generated_at": generated_at,
        "expires_at": expires_at,
        "gpu_per_node_multiple": multiple,
        "gpu_multiple_exempt_qos": exempt_qos,
        "personal_accounts": personal,
        "org_accounts": orgs,
        "project_accounts": projects,
        "home_aliases": aliases,
    }


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _lua_map(name: str, values: dict[str, str]) -> list[str]:
    lines = [f"    {name} = {{"]
    lines.extend(f"        [{_quoted(key)}] = {_quoted(values[key])}," for key in sorted(values))
    lines.append("    },")
    return lines


def render_lua(projection: dict[str, Any]) -> str:
    lines = [
        "return {",
        "    schema_version = 1,",
        f"    revision = {_quoted(projection['revision'])},",
        f"    generated_at = {projection['generated_at']},",
        f"    expires_at = {projection['expires_at']},",
        f"    gpu_per_node_multiple = {projection['gpu_per_node_multiple']},",
        "    gpu_multiple_exempt_qos = {",
    ]
    lines.extend(f"        [{_quoted(qos)}] = true," for qos in projection["gpu_multiple_exempt_qos"])
    lines.append("    },")
    lines.extend(_lua_map("personal_accounts", projection["personal_accounts"]))
    lines.extend(_lua_map("org_accounts", projection["org_accounts"]))
    lines.extend(_lua_map("project_accounts", projection["project_accounts"]))
    lines.extend(_lua_map("home_aliases", projection["home_aliases"]))
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
