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
_MANAGED_CONFIG_PATH = Path("/etc/sai-cli/config.toml")
_MANAGED_CONFIG_OWNER_UID = 0
_MANAGED_OVERRIDE_ENV = (
    "SAI_API_BASE_URL",
    "SAI_SITE_READ_BASE_URL",
    "SAI_SITE_ID",
    "SAI_CLUSTER_ID",
    "SAI_PROFILE",
    "SAI_API_USERNAME",
    "SAI_API_KEY_ID",
    "SAI_API_TIMEOUT",
    "SAI_TOKEN_CACHE",
    "SAI_ALLOW_INSECURE_HTTP",
    "SAI_API_SHARED_SECRET",
)
_PROFILE_KEYS = {
    "portal_base_url",
    "site_read_base_url",
    "site_id",
    "cluster_id",
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
    portal_base_url: str
    site_read_base_url: str
    site_id: str
    cluster_id: str
    username: str | None
    key_id: str
    timeout_seconds: float
    allow_insecure_http: bool
    cache_path: Path
    use_cache: bool
    profile: str
    managed_login_node: bool = False


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


def _read_config(path: Path, *, required_owner_uid: int | None = None) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ConfigError("the SAI config path must be a regular file")
        owner_ok = (
            before.st_uid == required_owner_uid
            if required_owner_uid is not None
            else before.st_uid in {0, os.getuid()}
        )
        if not owner_ok or before.st_mode & 0o022:
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
    managed = _parse_bool(
        env.get("SAI_MANAGED_LOGIN_NODE"),
        field="SAI_MANAGED_LOGIN_NODE",
    )
    if managed:
        override_args = (
            "config",
            "profile",
            "base_url",
            "site_read_base_url",
            "site",
            "cluster",
            "username",
            "key_id",
            "timeout",
            "cache",
            "allow_insecure_http",
        )
        if any(getattr(args, name, None) not in {None, False} for name in override_args):
            raise ConfigError("managed login-node connection settings cannot be overridden")
        configured_path = (env.get("SAI_CONFIG") or "").strip()
        if configured_path and Path(configured_path) != _MANAGED_CONFIG_PATH:
            raise ConfigError("managed login-node config path cannot be overridden")
        forbidden_env = [name for name in _MANAGED_OVERRIDE_ENV if (env.get(name) or "").strip()]
        if forbidden_env:
            raise ConfigError(
                "managed login-node connection environment cannot be overridden"
            )
        config_path = _MANAGED_CONFIG_PATH
        requested_profile = None
    else:
        config_path = (
            Path(args.config).expanduser()
            if args.config
            else default_config_path(env)
        )
        requested_profile = _first_text(args.profile, env.get("SAI_PROFILE"))
    config = _read_config(
        config_path,
        required_owner_uid=_MANAGED_CONFIG_OWNER_UID if managed else None,
    )
    profile_name, values = _profile(config, requested_profile)

    portal_base_url = _first_text(
        None if managed else args.base_url,
        None if managed else env.get("SAI_API_BASE_URL"),
        values.get("portal_base_url"),
    )
    if not portal_base_url:
        raise ConfigError(
            "missing SAI Portal base URL; set --base-url or SAI_API_BASE_URL"
        )
    site_read_base_url = _first_text(
        None if managed else args.site_read_base_url,
        None if managed else env.get("SAI_SITE_READ_BASE_URL"),
        values.get("site_read_base_url"),
    )
    if not site_read_base_url:
        raise ConfigError(
            "missing SAI site-read base URL; set --site-read-base-url or "
            "SAI_SITE_READ_BASE_URL"
        )
    site_id = _first_text(
        None if managed else args.site,
        None if managed else env.get("SAI_SITE_ID"),
        values.get("site_id"),
    )
    if not site_id:
        raise ConfigError("missing SAI site; set --site or SAI_SITE_ID")
    cluster_id = _first_text(
        None if managed else args.cluster,
        None if managed else env.get("SAI_CLUSTER_ID"),
        values.get("cluster_id"),
    )
    if not cluster_id:
        raise ConfigError("missing SAI cluster; set --cluster or SAI_CLUSTER_ID")

    username = None if managed else _first_text(
        args.username,
        env.get("SAI_API_USERNAME"),
        values.get("username"),
    )
    key_id = (
        "sai-cli"
        if managed
        else _first_text(
            args.key_id,
            env.get("SAI_API_KEY_ID"),
            values.get("key_id"),
            "sai-cli",
        )
        or "sai-cli"
    )
    timeout_raw = _first_text(
        None if managed else args.timeout,
        None if managed else env.get("SAI_API_TIMEOUT"),
        values.get("timeout_seconds"),
        "10",
    )
    insecure_raw: object = False if managed else args.allow_insecure_http
    if insecure_raw is None:
        insecure_raw = env.get("SAI_ALLOW_INSECURE_HTTP", values.get("allow_insecure_http"))
    cache_raw = _first_text(
        None if managed else args.cache,
        None if managed else env.get("SAI_TOKEN_CACHE"),
        values.get("cache_path"),
    )
    return Settings(
        portal_base_url=portal_base_url.rstrip("/"),
        site_read_base_url=site_read_base_url.rstrip("/"),
        site_id=site_id,
        cluster_id=cluster_id,
        username=username,
        key_id=key_id,
        timeout_seconds=_parse_timeout(timeout_raw),
        allow_insecure_http=_parse_bool(insecure_raw, field="allow_insecure_http"),
        cache_path=Path(cache_raw).expanduser() if cache_raw else default_cache_path(env),
        use_cache=not bool(args.no_cache),
        profile=profile_name,
        managed_login_node=managed,
    )
