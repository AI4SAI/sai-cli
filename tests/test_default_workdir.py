from __future__ import annotations

import os
from pathlib import Path
import pwd
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "site/shell/default_workdir.bash"
USER = pwd.getpwuid(os.getuid()).pw_name


def _resolve(tmp_path: Path, rows: str, *, native_exit: int = 0, interactive_command: str | None = None):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, content in {
        "scontrol": "printf '%s\\n' 'ClusterName = cluster-a'\n",
        "sacctmgr": 'printf "%s\\n" "$TEST_ASSOC_ROWS"\nexit "$TEST_NATIVE_EXIT"\n',
    }.items():
        executable = binaries / name
        executable.write_text("#!/bin/bash\n" + content)
        executable.chmod(0o755)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-ilc" if interactive_command else "-c",
         interactive_command or 'source "$1"; _sai_default_context', "bash", str(SCRIPT)],
        env={**os.environ, "HOME": str(tmp_path), "PATH": f"{binaries}:/usr/bin:/bin", "TEST_ASSOC_ROWS": rows,
             "TEST_NATIVE_EXIT": str(native_exit)},
        cwd=tmp_path,
        text=True, capture_output=True, timeout=10,
    )


@pytest.mark.parametrize("account,lineage,expected", [
    (f"private-{USER}", f"/private-{USER}", f"/home/{USER}"),  # public-scan: allow-test-vector
    ("org-example", "/org-example", f"/org/org-example/{USER}"),
    ("legacy-example", "/legacy-example", f"/org/legacy-example/{USER}"),
    ("proj-example", "/org-example/proj-example", "/org/org-example/proj-example"),
])
def test_default_identity_uses_own_site_association(tmp_path, account, lineage, expected):
    rows = f"cluster-a|{account}|{USER}|{lineage}/0-{USER}/"
    result = _resolve(tmp_path, rows + "\n" + rows)
    assert result.returncode == 0, result.stderr
    assert result.stdout == account + "\t" + expected + "\n"


@pytest.mark.parametrize("rows", [
    "",
    f"other-site|org-example|{USER}|/org-example/0-{USER}/",
    "cluster-a|org-example|someone-else|/org-example/0-someone-else/",
    f"cluster-a|private-someone-else|{USER}|/private-someone-else/0-{USER}/",
    f"cluster-a|proj-example|{USER}|/org-example/../proj-example/0-{USER}/",
    f"cluster-a|proj-example|{USER}|/org-example/proj-other/0-{USER}/",
    f"cluster-a|org-example|{USER}|/org-example/0-{USER}/|unexpected",
    f"cluster-a|org-example|{USER}|/org-example/0-{USER}/\n"
    f"cluster-a|org-other|{USER}|/org-other/0-{USER}/",
])
def test_unresolved_identity_never_emits_a_guessed_path(tmp_path, rows):
    result = _resolve(tmp_path, rows)
    assert result.returncode != 0
    assert result.stdout == ""


def test_native_failure_does_not_print_a_path_or_native_diagnostic(tmp_path):
    result = _resolve(tmp_path, "provider output", native_exit=1)
    assert result.returncode != 0
    assert result.stdout == result.stderr == ""


def test_noninteractive_source_preserves_directory_and_does_not_query(tmp_path):
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", 'source "$1"; pwd', "bash", str(SCRIPT)],
        cwd=tmp_path, text=True, capture_output=True, check=True,
    )
    assert result.stdout.strip() == str(tmp_path)
    assert result.stderr == ""


def test_nested_login_shell_keeps_the_directory_selected_by_the_user(tmp_path):
    rows = f"cluster-a|private-{USER}|{USER}|/private-{USER}/0-{USER}/"
    result = _resolve(tmp_path, rows, interactive_command=(
        'source "$1"; cd "$HOME"; '
        'bash --noprofile --norc -ilc \'source "$1"; pwd\' bash "$1"'
    ))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path)
