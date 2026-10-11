"""Create a portable profile from explicitly selected, public service metadata."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import tempfile
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from .config import _parse_bool, _parse_timeout, _profile, _read_config, default_config_path
from .errors import ConfigError, ContractError
from .oidc import OidcClient
from .transport import JsonTransport, normalize_base_url


def configure(args: argparse.Namespace, environ: Mapping[str, str], *, scope: str) -> dict:
    if _parse_bool(environ.get("SAI_MANAGED_LOGIN_NODE"), field="SAI_MANAGED_LOGIN_NODE"):
        raise ConfigError("This shared installation is already configured by its operator.")
    if any(getattr(args, name, None) not in (None, False) for name in
           ("base_url", "site", "cluster", "cache", "no_cache", "allow_insecure_http")):
        raise ConfigError("configure accepts the service URL, --config, --profile and --timeout.")
    path = (Path(args.config).expanduser() if args.config else default_config_path(environ)).absolute()
    existing = _read_config(path)
    profile, saved = _profile(existing, args.profile or environ.get("SAI_PROFILE"))
    base = normalize_base_url(args.service_url, allow_insecure_http=False)
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in args.service_url):
        raise ConfigError("The service URL is invalid.")
    timeout = _parse_timeout(args.timeout if args.timeout is not None else 10)
    response = JsonTransport(base_url=base, timeout_seconds=timeout, max_response_bytes=16384).request(
        "GET", "/v1/auth/config", query={"client": "sai-cli"})
    data = response.payload
    if (data.get("schema_version") != "cli.connection/v1" or data.get("oidc_client_id") != "sai-cli"
            or data.get("require_site_capability") is not True):
        raise ContractError("This service does not provide compatible CLI connection settings.")
    issuer, resource = data.get("identity_issuer"), data.get("oidc_resource")
    for value, maximum in ((issuer, 512), (resource, 255)):
        if (not isinstance(value, str) or not 1 <= len(value) <= maximum or not value.isascii()
                or any(character.isspace() or ord(character) < 33 or ord(character) == 127 for character in value)):
            raise ContractError("The service returned invalid CLI connection settings.")
    try:
        parsed = urlsplit(issuer)
        if urlsplit(base).scheme == "https" and parsed.scheme != "https":
            raise ValueError()
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        identity = OidcClient(transport=JsonTransport(base_url=origin, timeout_seconds=timeout, max_response_bytes=131072),
                              issuer_url=issuer, client_id="sai-cli", resource=resource, scope=scope)
        identity.discover()
    except ValueError as exc:
        raise ContractError("The service returned an invalid Identity issuer.") from exc
    values = {"base_url": base, "identity_issuer": identity.issuer_url, "oidc_client_id": identity.client_id,
              "oidc_scope": scope, "oidc_resource": resource, "require_site_capability": True}
    created = False
    if path.exists():
        if any(saved.get(key) != value for key, value in values.items() if key != "oidc_scope"):
            raise ConfigError("An existing configuration differs; choose a new --config path. Existing profiles were kept.",
                              code="configuration_exists")
    else:
        content = f"default_profile = {json.dumps(profile)}\n\n[profiles.{json.dumps(profile)}]\n"
        content += "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
        _create_profile(path, content)
        created = True
    options = (["--config", str(path)] if args.config else []) + (["--profile", profile] if args.profile else [])
    return {"schema_version": "cli.configured/v1", "created": created, "config_path": str(path),
            "profile": profile, "base_url": base, "identity_issuer": identity.issuer_url,
            "next_commands": [["sai", *options, "auth", "login"], ["sai", *options, "sites", "--format", "table"]]}


def _create_profile(path: Path, content: str) -> None:
    """Publish a complete private file without replacing another profile."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _read_config(path)
        info = path.parent.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ConfigError("The configuration directory must be owned by you and not writable by others.")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ConfigError("A configuration was created concurrently; retry without replacing it.", code="configuration_exists") from exc
    except OSError as exc:
        raise ConfigError("The configuration could not be saved; existing files were kept.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def render_configured(value: dict) -> str:
    status = "已保存连接" if value["created"] else "现有连接已验证"
    commands = "\n".join(shlex.join(command) for command in value["next_commands"])
    return f"{status}：{value['base_url']}\n登录服务：{value['identity_issuer']}\n\n{commands}\n"
