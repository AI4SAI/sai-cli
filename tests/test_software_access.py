from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


HELPER = Path(__file__).resolve().parents[1] / "site/modules/software_access.tcl"
HEADER = "# sai-software-access/v1\n"
EXAMPLE = HEADER + "example\t23456\tExample\n"


def _run(tmp_path: Path, install_root: Path, *, binding: str = EXAMPLE,
         key: str = "example", mode: str = "load", namespace: bool = False):
    table = tmp_path / "software-access.tsv"
    table.write_text(binding, encoding="utf-8")
    interpreter = shutil.which("tclsh") or shutil.which("tclsh8.6")
    assert interpreter, "Tcl is required to exercise the module helper"
    command = [interpreter, "/dev/stdin", str(HELPER), str(table), key, mode, str(install_root)]
    if namespace:
        bwrap = shutil.which("bwrap")
        if not bwrap:
            pytest.skip("the native user namespace test requires bubblewrap")
        command = [bwrap, "--unshare-user", "--ro-bind", "/", "/", "--dev", "/dev", "--proc",
                   "/proc", "--", *command]
    return subprocess.run(
        command,
        input="""
proc module-info {operation value} {return [expr {[lindex $::argv 3] eq $value}]}
encoding system iso8859-1
fconfigure stdout -encoding utf-8
fconfigure stderr -encoding utf-8
source -encoding utf-8 [lindex $argv 0]
set sai_software_access::binding_file [lindex $argv 1]
if {[catch {sai_require_software_access [lindex $argv 2] [lindex $argv 4]} message]} {
    puts stderr $message
    exit 42
}
""",
        text=True, capture_output=True, timeout=5,
        env={**os.environ, "GROUPS": "23456", "SAI_SOFTWARE_AUTHORIZED": "1"},
    )


@pytest.mark.parametrize("namespace", [False, True])
def test_current_process_can_load_an_accessible_installation(tmp_path: Path, namespace: bool) -> None:
    root = tmp_path / "vendor"
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    result = _run(tmp_path, root, key="third_app",
                  binding=HEADER + "third_app\t23456\tThird application\n", namespace=namespace)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.skipif(os.geteuid() == 0, reason="this denial requires an ordinary non-root file owner")
@pytest.mark.parametrize("namespace", [False, True])
def test_kernel_denial_is_preserved_despite_forged_group_environment(tmp_path: Path, namespace: bool) -> None:
    root = tmp_path / "vendor"
    root.mkdir()
    root.chmod(0o050)
    try:
        assert not os.access(root, os.R_OK | os.X_OK)
        result = _run(tmp_path, root, namespace=namespace)
    finally:
        root.chmod(0o700)
    assert (result.returncode, result.stdout, result.stderr) == (
        42, "", "Example 当前会话无权限：控制台开通；已开通请重新登录\n"
    )


@pytest.mark.parametrize("mode", ["display", "help", "spider", "remove"])
def test_readonly_and_unload_modes_do_not_require_access(tmp_path: Path, mode: str) -> None:
    result = _run(tmp_path, tmp_path / "missing", binding="invalid", mode=mode)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize("rows", [
    "unknown\t1234\tOther\n",
    "example\t0\tRoot\n",
    "example\t1234\tBad\x1b[31m\n",
    "example\t1234\tA\nexample\t1234\tB\n",
])
def test_missing_or_malformed_binding_fails_closed(tmp_path: Path, rows: str) -> None:
    root = tmp_path / "vendor"
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    result = _run(tmp_path, root, binding=HEADER + rows)
    assert (result.returncode, result.stdout, result.stderr) == (
        42, "", "软件访问配置不可用，请联系管理员\n"
    )


@pytest.mark.parametrize("invalid", ["public", "missing", "file", "alias"])
def test_requires_the_protected_installation_directory(tmp_path: Path, invalid: str) -> None:
    root = tmp_path / "vendor"
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    wrong = tmp_path / invalid
    if invalid == "public":
        wrong.mkdir()
        wrong.chmod(0o755)
    elif invalid == "alias":
        wrong.symlink_to(root, target_is_directory=True)
    elif invalid == "file":
        wrong.touch()
    result = _run(tmp_path, wrong)
    assert (result.returncode, result.stdout, result.stderr) == (
        42, "", "软件访问配置不可用，请联系管理员\n"
    )
