"""Non-secret configuration and profile resolution."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import tomllib
from typing import Any, Mapping

from .errors import ConfigError


_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PROFILE_KEYS = {
    "base_url",
    "site_id",
    "username",
    "key_id",
    "timeout_seconds",
    "allow_insecure_http",
    "cache_path",
}
_FORBIDDEN_PROFILE_KEYS = {
    "token",
    "bearer_token",
    "secret",
    "shared_secret",
    "password",
}


@dataclass(frozen=True)
class Settings:
    base_url: str
    site_id: str
    username: str | None
    key_id: str
    timeout_seconds: float
    allow_insecure_http: bool
    cache_path: Path
    use_cache: bool
    profile: str


def default_config_path(environ: Mapping[str, str]) -> Path:
    configured = (environ.get("SAI_CONFIG") or "").strip()
    if configured:
        return Path(configured).expanduser()
    xdg = (environ.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        return Path(xdg).expanduser() / "sai" / "config.toml"
    return Path.home() / ".config" / "sai" / "config.toml"


def default_cache_path(environ: Mapping[str, str]) -> Path:
    runtime = (environ.get("XDG_RUNTIME_DIR") or "").strip()
    if runtime:
        return Path(runtime).expanduser() / "sai" / "token-cache.json"
    cache_home = (environ.get("XDG_CACHE_HOME") or "").strip()
    if cache_home:
        return Path(cache_home).expanduser() / "sai" / "token-cache.json"
    return Path.home() / ".cache" / "sai" / "token-cache.json"


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ConfigError("the SAI config path must be a regular file")
        if before.st_uid not in {0, os.getuid()} or before.st_mode & 0o022:
            raise ConfigError("the SAI config file ownership or permissions are unsafe")
        if before.st_size > 1_048_576:
            raise ConfigError("the SAI config file is too large")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            after = os.fstat(handle.fileno())
            if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                raise ConfigError("the SAI config file changed while it was being read")
            loaded = tomllib.load(handle)
    except ConfigError:
        raise
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("the SAI config file could not be read") from exc
    if not isinstance(loaded, dict):
        raise ConfigError("the SAI config root must be a TOML table")
    unknown_root = set(loaded) - {"default_profile", "profiles"}
    if unknown_root:
        raise ConfigError("the SAI config file contains unsupported root keys")
    return loaded


def _profile(config: dict[str, Any], requested: str | None) -> tuple[str, dict[str, Any]]:
    default_name = config.get("default_profile", "default")
    name = (requested or str(default_name or "default")).strip()
    if not _PROFILE_RE.fullmatch(name):
        raise ConfigError("the SAI profile name is invalid")

    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigError("profiles must be a TOML table")
    raw = profiles.get(name, {})
    if not isinstance(raw, dict):
        raise ConfigError(f"SAI profile {name!r} must be a TOML table")

    keys = set(raw)
    if keys & _FORBIDDEN_PROFILE_KEYS:
        raise ConfigError("tokens and secrets are not allowed in the SAI config file")
    if keys - _PROFILE_KEYS:
        raise ConfigError(f"SAI profile {name!r} contains unsupported keys")
    return name, raw


def _first_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_bool(value: object, *, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{field} must be true or false")


def _parse_timeout(value: object) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("API timeout must be a number") from exc
    if timeout <= 0 or timeout > 120:
        raise ConfigError("API timeout must be greater than 0 and at most 120 seconds")
    return timeout


def resolve_settings(args: argparse.Namespace, environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    config_path = Path(args.config).expanduser() if args.config else default_config_path(env)
    config = _read_config(config_path)
    requested_profile = _first_text(args.profile, env.get("SAI_PROFILE"))
    profile_name, values = _profile(config, requested_profile)

    base_url = _first_text(args.base_url, env.get("SAI_API_BASE_URL"), values.get("base_url"))
    if not base_url:
        raise ConfigError("missing SAI API base URL; set --base-url or SAI_API_BASE_URL")
    site_id = _first_text(args.site, env.get("SAI_SITE_ID"), values.get("site_id"))
    if not site_id:
        raise ConfigError("missing SAI site; set --site or SAI_SITE_ID")

    username = _first_text(args.username, env.get("SAI_API_USERNAME"), values.get("username"))
    key_id = _first_text(args.key_id, env.get("SAI_API_KEY_ID"), values.get("key_id"), "sai-cli") or "sai-cli"
    timeout_raw = _first_text(args.timeout, env.get("SAI_API_TIMEOUT"), values.get("timeout_seconds"), "10")
    insecure_raw: object = args.allow_insecure_http
    if insecure_raw is None:
        insecure_raw = env.get("SAI_ALLOW_INSECURE_HTTP", values.get("allow_insecure_http"))
    cache_raw = _first_text(args.cache, env.get("SAI_TOKEN_CACHE"), values.get("cache_path"))

    return Settings(
        base_url=base_url.rstrip("/"),
        site_id=site_id,
        username=username,
        key_id=key_id,
        timeout_seconds=_parse_timeout(timeout_raw),
        allow_insecure_http=_parse_bool(insecure_raw, field="allow_insecure_http"),
        cache_path=Path(cache_raw).expanduser() if cache_raw else default_cache_path(env),
        use_cache=not bool(args.no_cache),
        profile=profile_name,
    )
