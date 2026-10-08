#!/usr/bin/env python3
"""Build one shared CLI release and its small node-integration package."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "sai-cli"
SOURCE_PATHS = (
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "packaging/login-node/config.toml.example",
    "packaging/login-node/sai",
    "scripts/build_login_node_deb.py",
)


def _run(*args: str) -> str:
    return subprocess.run(
        list(args),
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _git_provenance(*, allow_dirty: bool) -> tuple[str, str, bool, bool, int]:
    commit = _run("git", "rev-parse", "HEAD")
    if len(commit) != 40:
        raise RuntimeError("git commit is invalid")
    dirty = bool(_run("git", "status", "--porcelain"))
    if dirty and not allow_dirty:
        raise RuntimeError("formal login-node packages require a clean worktree")
    reachable = False
    if not allow_dirty:
        try:
            remote_main = _run("git", "rev-parse", "--verify", "refs/remotes/origin/main")
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, remote_main],
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "formal login-node packages require HEAD to be reachable from origin/main"
            ) from exc
        reachable = True
    timestamp = int(_run("git", "show", "-s", "--format=%ct", "HEAD"))
    stamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    return commit, f"0.1.0+{stamp}.{commit[:12]}", not dirty, reachable, timestamp


def _source_files(root: Path = REPO_ROOT) -> list[Path]:
    paths = [root / value for value in SOURCE_PATHS]
    paths.extend(sorted((root / "packaging/login-node").glob("*-requirements.txt")))
    paths.extend(sorted((root / "src" / "sai_cli").rglob("*.py")))
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise RuntimeError("login-node package source set is incomplete or unsafe")
    return sorted(set(paths))


def _source_digest(paths: list[Path], *, root: Path = REPO_ROOT) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _extract_git_archive(commit: str, destination: Path, *, timestamp: int) -> None:
    """Materialize only committed source into a deterministic build tree."""

    completed = subprocess.run(
        ["git", "archive", "--format=zip", commit],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(completed.stdout))
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError("git archive could not be read") from exc
    with archive:
        members = archive.infolist()
        names: set[str] = set()
        for member in members:
            name = PurePosixPath(member.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not name.parts
                or member.filename in names
            ):
                raise RuntimeError("git archive contains an unsafe member")
            names.add(member.filename)
            mode = member.external_attr >> 16
            if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise RuntimeError("git archive contains an unsafe member")
        archive.extractall(destination, members=members)
    for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        os.utime(path, (timestamp, timestamp), follow_symlinks=False)
    os.utime(destination, (timestamp, timestamp), follow_symlinks=False)


def _build_wheel(*, source_dir: Path, wheel_dir: Path, environment: dict[str, str]) -> None:
    """Build through the normal isolated PEP 517 frontend."""

    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)],
        cwd=source_dir,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_wheel_members(path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
    names: set[str] = set()
    for member in members:
        name = PurePosixPath(member.filename)
        if (
            name.is_absolute()
            or ".." in name.parts
            or not name.parts
            or member.filename in names
        ):
            raise RuntimeError("wheel contains an unsafe member")
        names.add(member.filename)
        mode = member.external_attr >> 16
        if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise RuntimeError("wheel contains a non-regular member")
    return members


def _write(path: Path, data: str | bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    path.chmod(mode)


@contextmanager
def _public_umask():
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def build(*, output_dir: Path, allow_dirty: bool = False, with_tui: bool = False) -> tuple[Path, Path]:
    """Build the package from the exact committed HEAD snapshot.

    ``allow_dirty`` exists for local tests and diagnostics only.  Even when it
    is true, the package input remains the committed HEAD archive and the
    manifest records ``source_clean=False``; uncommitted files are never
    silently mixed into a formal artifact.
    """

    commit, version, clean, remote_reachable, timestamp = _git_provenance(
        allow_dirty=allow_dirty
    )
    if with_tui:
        version += ".tui"
    # Validate the checkout-side package inputs before creating the archive.
    _source_files()
    output_dir = output_dir.resolve()
    with _public_umask(), tempfile.TemporaryDirectory(prefix="sai-cli-deb-") as temporary:
        output_dir.mkdir(parents=True, exist_ok=True)
        root = Path(temporary)
        source_dir = root / "source"
        _extract_git_archive(commit, source_dir, timestamp=timestamp)
        source_paths = _source_files(source_dir)
        source_sha256 = _source_digest(source_paths, root=source_dir)
        wheel_dir = root / "wheel"
        build_environment = os.environ.copy()
        build_environment["SOURCE_DATE_EPOCH"] = str(timestamp)
        _build_wheel(
            source_dir=source_dir,
            wheel_dir=wheel_dir,
            environment=build_environment,
        )
        wheels = list(wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("wheel build did not produce exactly one artifact")
        wheel = wheels[0]
        _safe_wheel_members(wheel)

        stage = root / PACKAGE_NAME
        release_rel = PurePosixPath("cli/releases") / version / "site-packages"
        shared = root / "shared"
        release = shared / str(release_rel)
        release.mkdir(parents=True)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(release)
        dependencies = []
        if with_tui:
            dependency_dir = root / "tui-wheels"
            subprocess.run([
                sys.executable, "-m", "pip", "download", "--no-cache-dir", "--no-deps", "--require-hashes",
                "--only-binary=:all:", "--dest", str(dependency_dir), "-r",
                str(source_dir / "packaging/login-node/tui-requirements.txt"),
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=build_environment)
            for dependency in sorted(dependency_dir.glob("*.whl")):
                if not dependency.name.endswith("none-any.whl"):
                    raise RuntimeError("shared terminal dependencies must be pure Python wheels")
                _safe_wheel_members(dependency)
                with zipfile.ZipFile(dependency) as archive:
                    archive.extractall(release)
                dependencies.append({"wheel": dependency.name, "sha256": _sha256(dependency)})
        for path in release.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)

        wrapper = (source_dir / "packaging/login-node/sai").read_text(encoding="utf-8")
        wrapper = wrapper.replace("@SAI_CLI_PYTHONPATH@", f"/opt/sai/{release_rel.as_posix()}")
        _write(shared / "cli/releases" / version / "bin/sai", wrapper, mode=0o755)
        for name, selector in (("stat_job", ""), ("stat_job_all", "--user '*' ")):
            native_wrapper = (f'#!/bin/sh\nset -eu\nexec "/opt/sai/cli/releases/{version}/bin/sai" '
                              f'jobs local --format table {selector}"$@"\n')
            _write(shared / "cli/releases" / version / "bin" / name, native_wrapper, mode=0o755)
        (stage / "usr/bin").mkdir(parents=True)
        (stage / "usr/bin/sai").symlink_to("/opt/sai/bin/sai")
        _write(
            stage / "usr/share/sai-cli/examples/config.toml",
            (source_dir / "packaging/login-node/config.toml.example").read_bytes(),
            mode=0o644,
        )

        shared_artifact = output_dir / f"sai-cli-runtime_{version}.tar.gz"
        if shared_artifact.exists():
            raise RuntimeError(f"refusing to overwrite existing artifact: {shared_artifact}")
        with shared_artifact.open("wb") as raw, gzip.GzipFile(
            filename="", fileobj=raw, mode="wb", mtime=timestamp
        ) as compressed, tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(shared.rglob("*")):
                info = archive.gettarinfo(str(path), arcname=path.relative_to(shared).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = timestamp
                info.mode = 0o755 if path.is_dir() or path.name in {"sai", "stat_job", "stat_job_all"} else 0o644
                if path.is_file():
                    with path.open("rb") as content:
                        archive.addfile(info, content)
                else:
                    archive.addfile(info)
        shared_files = sorted(
            "/opt/sai/" + path.relative_to(shared).as_posix()
            for path in shared.rglob("*") if path.is_file()
        )

        installed_files = sorted(
            "/" + path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if (path.is_file() or path.is_symlink())
            and "DEBIAN" not in path.relative_to(stage).parts
        )
        installed_files.append("/usr/share/sai-cli/package-manifest.json")
        installed_files.sort()
        manifest = {
            "schema_version": "sai-cli-login-package/v2",
            "source_package": "sai-cli",
            "binary_package": PACKAGE_NAME,
            "role": "login_node_cli",
            "version": version,
            "git_commit": commit,
            "source_clean": clean,
            "remote_reachable": remote_reachable,
            "source_sha256": source_sha256,
            "wheel_filename": wheel.name,
            "wheel_sha256": _sha256(wheel),
            "runtime_dependencies": dependencies,
            "credential_files": [],
            "installed_files": installed_files,
            "activation_entrypoint": "/opt/sai/bin/sai",
            "shared_release": {
                "artifact": shared_artifact.name,
                "sha256": _sha256(shared_artifact),
                "prefix": f"/opt/sai/cli/releases/{version}",
                "installed_files": shared_files,
            },
            "compatibility_entrypoints": ["/usr/bin/sai"],
            "rollback": {
                "strategy": "dpkg-reinstall",
                "command": "dpkg -i /path/to/recorded-previous-sai-cli.deb",
                "scope": "node integration package; shared CLI selection is restored separately",
            },
        }
        _write(
            stage / "usr/share/sai-cli/package-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            mode=0o644,
        )
        control = (
            f"Package: {PACKAGE_NAME}\n"
            f"Version: {version}\n"
            "Section: science\n"
            "Priority: optional\n"
            "Architecture: all\n"
            "Maintainer: SAI Operations <ops@example.invalid>\n"
            "Depends: python3 (>= 3.11)\n"
            "Description: Node integration for the shared SAI client\n"
            " Installs only the PATH entry and non-secret example; client code is published once in the shared platform tree.\n"
        )
        _write(stage / "DEBIAN/control", control, mode=0o644)
        postinst = """#!/bin/sh
set -eu
/usr/bin/sai --version >/dev/null
exit 0
"""
        _write(stage / "DEBIAN/postinst", postinst, mode=0o755)

        artifact = output_dir / f"{PACKAGE_NAME}_{version}_all.deb"
        if artifact.exists():
            raise RuntimeError(f"refusing to overwrite existing artifact: {artifact}")
        subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", str(stage), str(artifact)],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=build_environment,
        )
        artifact_manifest = output_dir / f"{artifact.name}.manifest.json"
        release_manifest = {
            **manifest,
            "artifact": artifact.name,
            "artifact_sha256": _sha256(artifact),
            "artifact_size": artifact.stat().st_size,
        }
        _write(
            artifact_manifest,
            json.dumps(release_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            mode=0o600,
        )
        return artifact, artifact_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist" / "deb")
    parser.add_argument("--allow-dirty", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--with-tui", action="store_true", help="bundle the pinned terminal UI dependencies in the shared release")
    args = parser.parse_args()
    artifact, manifest = build(output_dir=args.output_dir, allow_dirty=args.allow_dirty, with_tui=args.with_tui)
    print(f"SAI_CLI_DEB={artifact}")
    print(f"SAI_CLI_DEB_MANIFEST={manifest}")
    print(f"SAI_CLI_DEB_SHA256={_sha256(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
