from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts.build_login_node_deb import build


def test_login_node_package_is_role_scoped_and_provenance_bound(tmp_path: Path) -> None:
    artifact, manifest_path = build(output_dir=tmp_path, allow_dirty=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert artifact.is_file()
    assert manifest["schema_version"] == "sai-cli-login-package/v1"
    assert len(manifest["git_commit"]) == 40
    assert len(manifest["source_sha256"]) == 64
    assert len(manifest["wheel_sha256"]) == 64
    assert manifest["remote_reachable"] is False
    assert manifest["runtime_dependencies"] == []
    assert manifest["credential_files"] == []
    assert manifest["rollback"]["strategy"] == "dpkg-reinstall"

    listing = subprocess.run(
        ["dpkg-deb", "-c", str(artifact)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    assert "./usr/bin/sai" in listing
    assert "./usr/share/sai-cli/package-manifest.json" in listing
    assert "sai_site_runtime" not in listing
    assert "sai_core" not in listing
    assert "/etc/sai-cli/config.toml" not in listing
    assert "DEBIAN" not in listing


def test_managed_wrapper_forces_capability_mode_without_secret_inputs() -> None:
    wrapper = (Path(__file__).parents[1] / "packaging/login-node/sai").read_text(
        encoding="utf-8"
    )
    assert "SAI_ENV=production" in wrapper
    assert "SAI_MANAGED_LOGIN_NODE=1" in wrapper
    assert "SAI_CONFIG=/etc/sai-cli/config.toml" in wrapper
    assert "python3 -I -P -c" in wrapper
    assert "SAI_TOKEN" not in wrapper
    assert "SHARED_SECRET" not in wrapper
    assert "squeue" not in wrapper


def test_login_node_wrapper_is_valid_shell() -> None:
    wrapper = Path(__file__).parents[1] / "packaging/login-node/sai"
    subprocess.run(["sh", "-n", str(wrapper)], check=True)


def test_login_node_config_matches_current_settings_contract() -> None:
    config = (Path(__file__).parents[1] / "packaging/login-node/config.toml.example").read_text(
        encoding="utf-8"
    )
    assert 'portal_base_url = "https://portal.example.org"' in config
    assert 'site_read_base_url = "https://site-read.example.org"' in config
    assert 'cluster_id = "cluster-a"' in config
    assert "\nbase_url =" not in config
