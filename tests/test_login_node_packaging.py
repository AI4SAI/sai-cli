from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import scripts.build_login_node_deb as build_module
from scripts.build_login_node_deb import build


_HAS_SETUPTOOLS = importlib.util.find_spec("setuptools") is not None


@pytest.fixture
def local_standard_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the real backend without network only when it is locally installed."""

    if not _HAS_SETUPTOOLS:
        pytest.skip("standard PEP 517 package tests require an installed setuptools backend")
    real_run = build_module.subprocess.run

    def run(command, *args, **kwargs):
        command = list(command)
        if command[:3] == [build_module.sys.executable, "-m", "build"]:
            command.append("--no-isolation")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(build_module.subprocess, "run", run)


def test_login_node_package_is_role_scoped_and_provenance_bound(
    tmp_path: Path, local_standard_builder: None
) -> None:
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
    assert "python3 -I -P -B -c" in wrapper
    assert "SAI_TOKEN" not in wrapper
    assert "SHARED_SECRET" not in wrapper
    assert "squeue" not in wrapper


def test_login_node_wrapper_is_valid_shell() -> None:
    wrapper = Path(__file__).parents[1] / "packaging/login-node/sai"
    subprocess.run(["sh", "-n", str(wrapper)], check=True)


def test_login_node_wrapper_does_not_write_bytecode(tmp_path: Path) -> None:
    package_root = tmp_path / "site-packages"
    shutil.copytree(
        Path(__file__).parents[1] / "src" / "sai_cli",
        package_root / "sai_cli",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    wrapper = tmp_path / "sai"
    template = (Path(__file__).parents[1] / "packaging/login-node/sai").read_text(
        encoding="utf-8"
    )
    wrapper.write_text(
        template.replace("@SAI_CLI_PYTHONPATH@", str(package_root)),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    subprocess.run([str(wrapper), "--version"], check=True, text=True, stdout=subprocess.PIPE)
    assert not list(package_root.rglob("*.pyc"))


def test_ignored_build_payload_is_not_packaged(
    tmp_path: Path, local_standard_builder: None
) -> None:
    stale_dir = build_module.REPO_ROOT / "build" / "lib" / "sai_cli"
    stale_dir.mkdir(parents=True, exist_ok=True)
    stale = stale_dir / f"_stale_payload_{os.getpid()}.py"
    assert not stale.exists()
    stale.write_text("raise RuntimeError('stale build payload')\n", encoding="utf-8")
    try:
        artifact, manifest_path = build(output_dir=tmp_path, allow_dirty=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert not any("_stale_payload_" in path for path in manifest["installed_files"])
        listing = subprocess.run(
            ["dpkg-deb", "-c", str(artifact)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert "_stale_payload_" not in listing
    finally:
        stale.unlink()


def test_repeated_clean_head_builds_are_byte_identical(
    tmp_path: Path, local_standard_builder: None
) -> None:
    first, first_manifest = build(output_dir=tmp_path / "first", allow_dirty=True)
    second, second_manifest = build(output_dir=tmp_path / "second", allow_dirty=True)
    assert first.read_bytes() == second.read_bytes()
    assert first_manifest.read_bytes() == second_manifest.read_bytes()


def test_login_node_config_matches_current_settings_contract() -> None:
    config = (Path(__file__).parents[1] / "packaging/login-node/config.toml.example").read_text(
        encoding="utf-8"
    )
    assert 'base_url = "https://portal.example.org"' in config
    assert 'cluster_id = "cluster-a"' in config
    assert "require_site_capability = true" in config
    assert "site_read_base_url" not in config
