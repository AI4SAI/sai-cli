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
def test_connection_site_is_valid_before_or_after_command(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    assert args.site == "site-a"
    assert args.cluster == "cluster-a"


def test_profile_loads_and_cli_environment_precedence(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
default_profile = "lab"

[profiles.lab]
base_url = "https://profile.example.org"
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
            "SAI_SITE_ID": "environment-site",
            "SAI_API_USERNAME": "environment-user",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        },
    )

    assert settings.base_url == "https://environment.example.org"
    assert settings.site_id == "cli-site"
    assert settings.cluster_id == "profile-cluster"
    assert settings.username == "environment-user"
    assert settings.key_id == "profile-key"
    assert settings.timeout_seconds == 7
    assert settings.cache_path == tmp_path / "cache" / "sai" / "token-cache.json"
    assert settings.require_site_capability is False


@pytest.mark.parametrize(
    "key",
    ["token", "bearer_token", "secret", "shared_secret", "password"],
)
def test_profile_rejects_secrets(tmp_path: Path, key: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[profiles.default]\n"
        'base_url = "https://example.org"\n'
        'site_id = "site-a"\n'
        f'{key} = "value"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)

    with pytest.raises(ConfigError, match="not allowed"):
        resolve_settings(_args("--config", str(config)), {})


def test_profile_rejects_direct_gateway_fields(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[profiles.default]\n"
        'base_url = "https://example.org"\n'
        'site_id = "site-a"\n'
        'site_read_base_url = "https://gateway.example.org"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)

    with pytest.raises(ConfigError, match="unsupported keys"):
        resolve_settings(_args("--config", str(config)), {})


def test_missing_base_url_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing SAI API base URL"):
        resolve_settings(
            _args("--config", str(tmp_path / "missing.toml"), "--site", "site-a"),
            {},
        )


@pytest.mark.parametrize("timeout", ["nan", "inf", "-inf"])
def test_nonfinite_timeout_is_rejected(tmp_path: Path, timeout: str) -> None:
    with pytest.raises(ConfigError, match="at most 120"):
        resolve_settings(
            _args(
                "--config",
                str(tmp_path / "missing.toml"),
                "--base-url",
                "https://example.org",
                "--site",
                "site-a",
                f"--timeout={timeout}",
            ),
            {},
        )


def test_group_writable_config_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[profiles.default]\n"
        'base_url = "https://example.org"\n'
        'site_id = "site-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o664)

    with pytest.raises(ConfigError, match="permissions are unsafe"):
        resolve_settings(_args("--config", str(config)), {})


def test_dangling_config_symlink_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.symlink_to(tmp_path / "missing.toml")

    with pytest.raises(ConfigError, match="regular file"):
        resolve_settings(_args("--config", str(config)), {})


def test_config_parent_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    config = link / "config.toml"
    with pytest.raises(ConfigError, match="symbolic links"):
        resolve_settings(
            _args(
                "--config",
                str(config),
                "--base-url",
                "https://example.org",
                "--site",
                "site-a",
            ),
            {},
        )


def test_managed_config_parent_permissions_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "managed"
    parent.mkdir()
    parent.chmod(0o777)
    config = parent / "config.toml"
    config.write_text(
        '[profiles.default]\nbase_url = "https://portal.example.org"\nsite_id = "site-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_PATH", config)
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_OWNER_UID", os.getuid())

    with pytest.raises(ConfigError, match="parent ownership or permissions"):
        resolve_settings(
            _args(),
            {"SAI_MANAGED_LOGIN_NODE": "1"},
        )


def test_managed_config_parent_must_be_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "managed"
    parent.write_text("not a directory", encoding="utf-8")
    config = parent / "config.toml"
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_PATH", config)
    monkeypatch.setattr(config_module, "_MANAGED_CONFIG_OWNER_UID", os.getuid())

    with pytest.raises(ConfigError, match="parent must be a directory"):
        resolve_settings(
            _args(),
            {"SAI_MANAGED_LOGIN_NODE": "1"},
        )


def test_unmanaged_config_allows_user_parent_permissions(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "user-config"
    parent.mkdir()
    parent.chmod(0o777)
    config = parent / "config.toml"
    config.write_text(
        '[profiles.default]\nbase_url = "https://portal.example.org"\nsite_id = "site-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o644)

    settings = resolve_settings(
        _args("--config", str(config)),
        {},
    )

    assert settings.base_url == "https://portal.example.org"
    assert settings.site_id == "site-a"


def test_managed_login_node_uses_root_config_and_token_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "managed.toml"
    config.write_text(
        "[profiles.default]\n"
        'base_url = "https://portal.example.org"\n'
        'site_id = "site-a"\n'
        'cluster_id = "cluster-a"\n'
        'require_site_capability = true\n',
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
            "SAI_TOKEN": "short-lived",
        },
    )

    assert settings.managed_login_node is True
    assert settings.base_url == "https://portal.example.org"
    assert settings.site_id == "site-a"
    assert settings.username is None
    assert settings.require_site_capability is True


def test_managed_login_node_rejects_connection_overrides() -> None:
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


def test_production_environment_requires_capability() -> None:
    with pytest.raises(ConfigError, match="capability is required"):
        resolve_settings(
            _args(
                "--base-url",
                "https://portal.example.org",
                "--site",
                "site-a",
            ),
            {"SAI_ENV": "production"},
        )
