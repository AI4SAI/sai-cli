from __future__ import annotations

from pathlib import Path
import os

import pytest

from sai_cli.cli import build_parser
import sai_cli.config as config_module
from sai_cli.config import resolve_settings
from sai_cli.errors import ConfigError


def _args(*extra: str):
    return build_parser().parse_args([*extra, "jobs", "list"])


@pytest.mark.parametrize(
    "argv",
    [
        ["--site", "site-a", "--cluster", "cluster-a", "jobs", "list"],
        ["jobs", "list", "--site", "site-a", "--cluster", "cluster-a"],
    ],
)
def test_connection_site_and_cluster_work_before_or_after_command(
    argv: list[str],
) -> None:
    args = build_parser().parse_args(argv)
    assert args.site == "site-a"
    assert args.cluster == "cluster-a"


def test_profile_loads_and_cli_environment_precedence(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
default_profile = "lab"

[profiles.lab]
portal_base_url = "https://profile.example.org"
site_read_base_url = "https://profile-read.example.org"
site_id = "profile-site"
cluster_id = "profile-cluster"
username = "profile-user"
key_id = "profile-key"
timeout_seconds = 7
""".strip(),
        encoding="utf-8",
    )
    config.chmod(0o644)
    args = _args("--config", str(config), "--site", "cli-site")

    settings = resolve_settings(
        args,
        {
            "SAI_API_BASE_URL": "https://environment.example.org",
            "SAI_SITE_READ_BASE_URL": "https://read.environment.example.org",
            "SAI_CLUSTER_ID": "environment-cluster",
            "SAI_API_USERNAME": "environment-user",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        },
    )

    assert settings.portal_base_url == "https://environment.example.org"
    assert settings.site_read_base_url == "https://read.environment.example.org"
    assert settings.site_id == "cli-site"
    assert settings.cluster_id == "environment-cluster"
    assert settings.username == "environment-user"
    assert settings.key_id == "profile-key"
    assert settings.timeout_seconds == 7
    assert settings.cache_path == tmp_path / "cache" / "sai" / "token-cache.json"


@pytest.mark.parametrize("key", ["token", "bearer_token", "secret", "shared_secret", "password"])
def test_profile_rejects_secrets(tmp_path: Path, key: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[profiles.default]\n"
        'portal_base_url = "https://example.org"\n'
        'site_read_base_url = "https://read.example.org"\n'
        'site_id = "site-a"\n'
        'cluster_id = "cluster-a"\n'
        f'{key} = "value"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)

    with pytest.raises(ConfigError, match="not allowed"):
        resolve_settings(_args("--config", str(config)), {})


def test_missing_portal_base_url_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing SAI Portal base URL"):
        resolve_settings(
            _args("--config", str(tmp_path / "missing.toml"), "--site", "site-a"),
            {
                "SAI_SITE_READ_BASE_URL": "https://read.example.org",
                "SAI_CLUSTER_ID": "cluster-a",
            },
        )


def test_timeout_and_boolean_are_validated(tmp_path: Path) -> None:
    args = _args(
        "--config",
        str(tmp_path / "missing.toml"),
        "--base-url",
        "https://example.org",
        "--site",
        "site-a",
    )
    with pytest.raises(ConfigError, match="true or false"):
        resolve_settings(
            args,
            {
                "SAI_SITE_READ_BASE_URL": "https://read.example.org",
                "SAI_CLUSTER_ID": "cluster-a",
                "SAI_ALLOW_INSECURE_HTTP": "maybe",
            },
        )


def test_group_writable_config_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[profiles.default]\n"
        'portal_base_url = "https://example.org"\n'
        'site_read_base_url = "https://read.example.org"\n'
        'site_id = "site-a"\n'
        'cluster_id = "cluster-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o664)

    with pytest.raises(ConfigError, match="permissions are unsafe"):
        resolve_settings(_args("--config", str(config)), {})


def test_managed_login_node_uses_only_root_managed_connection_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "managed.toml"
    config.write_text(
        "[profiles.default]\n"
        'portal_base_url = "https://portal.example.org"\n'
        'site_read_base_url = "http://127.0.0.1:9180"\n'
        'site_id = "site-a"\n'
        'cluster_id = "cluster-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_PATH", config)
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_OWNER_UID", os.getuid())

    settings = resolve_settings(
        _args(),
        {
            "SAI_MANAGED_LOGIN_NODE": "1",
            "SAI_CONFIG": str(config),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        },
    )

    assert settings.managed_login_node is True
    assert settings.portal_base_url == "https://portal.example.org"
    assert settings.site_read_base_url == "http://127.0.0.1:9180"
    assert settings.username is None


def test_managed_login_node_rejects_argv_env_and_hmac_overrides(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigError, match="cannot be overridden"):
        resolve_settings(
            _args("--base-url", "https://attacker.example.org"),
            {"SAI_MANAGED_LOGIN_NODE": "1"},
        )
    with pytest.raises(ConfigError, match="cannot be overridden"):
        resolve_settings(
            _args(),
            {
                "SAI_MANAGED_LOGIN_NODE": "1",
                "SAI_API_SHARED_SECRET": "must-not-be-used",
            },
        )
