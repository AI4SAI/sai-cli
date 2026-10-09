"""Shared native input, observation and value boundaries; no Portal dependency."""

from __future__ import annotations

import argparse
import math
import os
from typing import Any, Mapping

from .errors import ConfigError, ContractError, UnavailableError


def invalid_native() -> ContractError:
    return ContractError("Slurm returned invalid native data", code="native_response_invalid")


def native_text(value: object, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > 4096 or (required and not value):
        raise invalid_native()
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise invalid_native() from exc
    return "".join(f"\\x{ord(char):02x}" if ord(char) < 32 or 127 <= ord(char) <= 159 else char
                   for char in value)


def native_number(value: object) -> int | None:
    if isinstance(value, dict):
        if type(value.get("set")) is not bool or type(value.get("infinite")) is not bool:
            raise invalid_native()
        if not value["set"] or value["infinite"]:
            return None
        value = value.get("number")
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < 2**63:
        raise invalid_native()
    return value


def local_options(args: argparse.Namespace, *, command: str) -> float:
    for name in ("config", "profile", "base_url", "site", "cluster", "cache", "no_cache", "allow_insecure_http"):
        if getattr(args, name, None) not in (None, False):
            raise ConfigError(f"{command} uses this host's native context, not --{name.replace('_', '-')}")
    timeout = args.timeout if args.timeout is not None else 10.0
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ConfigError("--timeout must be greater than zero and at most 120 seconds")
    return timeout


def native_user() -> str:
    try:
        import pwd
    except ImportError as exc:
        raise UnavailableError("local native queries require a Unix environment",
                               code="native_client_unavailable") from exc
    return pwd.getpwuid(os.geteuid()).pw_name


def native_environment(environ: Mapping[str, str], *, filter_prefix: str) -> dict[str, str]:
    return {key: value for key, value in environ.items() if not key.startswith((filter_prefix, "SAI_", "_SAI_"))}


def native_header(payload: dict[str, Any]) -> tuple[str, int]:
    if not isinstance(payload.get("errors"), list) or not isinstance(payload.get("warnings"), list):
        raise invalid_native()
    if payload["errors"]:
        raise UnavailableError("Slurm reported a query error", code="native_query_failed")
    meta = payload.get("meta")
    slurm = meta.get("slurm") if isinstance(meta, dict) else None
    if not isinstance(slurm, dict):
        raise invalid_native()
    return native_text(slurm.get("cluster"), required=True), len(payload["warnings"])
