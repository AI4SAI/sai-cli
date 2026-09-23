from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


HELPER = Path(__file__).resolve().parents[1] / "site/modules/software_access.tcl"
HEADER = "# sai-software-access/v1\n"


def _run(tmp_path: Path, text: str, *, key: str = "example", mode: str = "load", groups: str = ""):
    binding = tmp_path / "software-access.tsv"
    binding.write_text(text, encoding="utf-8")
    interpreter = shutil.which("tclsh")
    assert interpreter, "Tcl is required to exercise the actual module helper"
    return subprocess.run(
        [interpreter, "/dev/stdin", str(HELPER), str(binding), key, mode, groups],
        input="""
proc module-info {operation value} {return [expr {[lindex $::argv 3] eq $value}]}
encoding system iso8859-1
fconfigure stdout -encoding utf-8
fconfigure stderr -encoding utf-8
source -encoding utf-8 [lindex $argv 0]
set sai_software_access::binding_file [lindex $argv 1]
if {[lindex $argv 4] ne ""} {
    rename exec native_exec
    proc exec {args} {
        if {$args ne {/usr/bin/id -G}} {error "unexpected external command"}
        return [lindex $::argv 4]
    }
}
if {[catch {sai_require_software_access [lindex $argv 2]} message]} {
    puts stderr $message
    exit 42
}
""",
        text=True, capture_output=True, timeout=5,
        env={**os.environ, "GROUPS": "23456", "SAI_SOFTWARE_AUTHORIZED": "1"},
    )


def test_real_process_groups_are_used_and_environment_cannot_grant_access(tmp_path: Path) -> None:
    groups = set(os.getgroups()) | {os.getegid()}
    positive = groups - {0}
    if positive:
        allowed = _run(tmp_path, HEADER + f"example\t{min(positive)}\tExample\n")
        assert (allowed.returncode, allowed.stdout, allowed.stderr) == (0, "", "")
    denied_gid = 23456 if 23456 not in groups else 23457
    denied = _run(tmp_path, HEADER + f"example\t{denied_gid}\tExample\n")
    assert denied.returncode == 42
    assert denied.stdout == ""
    assert denied.stderr == "Example 当前会话无权限：控制台开通；已开通请重新登录\n"


@pytest.mark.parametrize("groups", ["23456 1000", "1000 23456"])
def test_primary_or_supplementary_group_uses_same_checker(tmp_path: Path, groups: str) -> None:
    result = _run(tmp_path, HEADER + "third_app\t23456\tThird application\n", key="third_app", groups=groups)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize("mode", ["display", "help", "spider", "remove"])
def test_readonly_and_unload_modes_do_not_require_access(tmp_path: Path, mode: str) -> None:
    result = _run(tmp_path, "invalid", mode=mode, groups="unreadable")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize("rows", [
    "unknown\t1234\tOther\n",
    "example\t0\tRoot\n",
    "example\t1234\tBad\x1b[31m\n",
    "example\t1234\tA\nexample\t1234\tB\n",
])
def test_missing_or_malformed_binding_fails_closed(tmp_path: Path, rows: str) -> None:
    result = _run(tmp_path, HEADER + rows, groups="1234")
    assert result.returncode == 42
    assert result.stdout == ""
    assert result.stderr == "软件访问配置不可用，请联系管理员\n"
