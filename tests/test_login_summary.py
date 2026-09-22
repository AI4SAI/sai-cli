import os
from pathlib import Path
import subprocess


FRAGMENT = Path(__file__).resolve().parents[1] / "site/shell/login_summary.bash"


def test_login_summary_runs_once_preserves_shell_and_passes_applied_account(tmp_path):
    command = tmp_path / "sai"
    command.write_text('#!/bin/bash\nprintf "CALL:%s\\n" "$*"\nexit 3\n')
    command.chmod(0o755)
    fragment = tmp_path / "login.bash"
    fragment.write_text(FRAGMENT.read_text().replace('/opt/sai/bin/sai', str(command)))
    env = {k: v for k, v in os.environ.items() if k not in {
        '_SAI_LOGIN_SUMMARY_SHOWN', 'SLURM_JOB_ID', 'SLURM_JOBID',
    }}
    env["HOSTNAME"] = "login-example"
    result = subprocess.run(['bash', '--noprofile', '--norc', '-ilc',
        '_SAI_LOGIN_ACCOUNT=org-example; source "$1"; source "$1"; '
        'bash --noprofile --norc -ilc \'source "$1"\' bash "$1"; printf "SHELL-READY\\n"',
        'bash', str(fragment)], env=env, text=True, capture_output=True, timeout=6)
    assert result.returncode == 0 and result.stdout.count('CALL:') == 1, result.stderr
    assert 'status --format tui --account org-example' in result.stdout
    assert result.stdout.endswith('SHELL-READY\n')
    for flags, skip in (('-c', {}), ('-ilc', {'SLURM_JOB_ID': '123'}),
                        ('-ilc', {'SLURM_JOBID': '123'}), ('-ilc', {'HOSTNAME': 'compute-example'})):
        result = subprocess.run(['bash', '--noprofile', '--norc', flags, 'source "$1"', 'bash', str(fragment)],
            env={**env, **skip}, text=True, capture_output=True, timeout=6)
        assert not result.stdout
