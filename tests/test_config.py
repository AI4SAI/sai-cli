from __future__ import annotations

from pathlib import Path

import pytest

from sai_cli.cli import build_parser
from sai_cli.config import resolve_settings
from sai_cli.errors import ConfigError


def _args(*extra: str):
    return build_parser().parse_args([*extra, "jobs", "list"])


def test_profile_loads_and_cli_environment_precedence(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
default_profile = "lab"

[profiles.lab]
base_url = "https://profile.example.org"
site_id = "profile-site"
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
            "SAI_API_USERNAME": "environment-user",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        },
    )

    assert settings.base_url == "https://environment.example.org"
    assert settings.site_id == "cli-site"
    assert settings.username == "environment-user"
    assert settings.key_id == "profile-key"
    assert settings.timeout_seconds == 7
    assert settings.cache_path == tmp_path / "cache" / "sai" / "token-cache.json"


@pytest.mark.parametrize("key", ["token", "bearer_token", "secret", "shared_secret", "password"])
def test_profile_rejects_secrets(tmp_path: Path, key: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"[profiles.default]\nbase_url = \"https://example.org\"\nsite_id = \"site-a\"\n{key} = \"value\"\n",
        encoding="utf-8",
    )
    config.chmod(0o644)

    with pytest.raises(ConfigError, match="not allowed"):
        resolve_settings(_args("--config", str(config)), {})


def test_missing_base_url_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing SAI API base URL"):
        resolve_settings(
            _args("--config", str(tmp_path / "missing.toml"), "--site", "site-a"),
            {},
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
        resolve_settings(args, {"SAI_ALLOW_INSECURE_HTTP": "maybe"})


def test_group_writable_config_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[profiles.default]\nbase_url = "https://example.org"\nsite_id = "site-a"\n',
        encoding="utf-8",
    )
    config.chmod(0o664)

    with pytest.raises(ConfigError, match="permissions are unsafe"):
        resolve_settings(_args("--config", str(config)), {})
