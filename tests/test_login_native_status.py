import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from test_local_resources import native_client


SHELL = Path(__file__).resolve().parents[1] / "site/shell"


def run_status(tmp_path, native_client, *, login=False):
    environment, _, _ = native_client
    source = Path(__file__).resolve().parents[1] / "src"
    command = tmp_path / "sai"
    command.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m sai_cli "$@"\n')
    command.chmod(0o755)
    fragment = tmp_path / "status.bash"
    fragment.write_text((SHELL / "status.bash").read_text())
    if login:
        for name in ("aliases.txt", "rules.bash", "notes.bash"):
            (tmp_path / name).write_text("")
        summary = tmp_path / "summary"
        summary.write_text('#!/bin/sh\nprintf "ACCOUNT-SUMMARY\\n"\n')
        summary.chmod(0o755)
        fragment = tmp_path / "login.bash"
        fragment.write_text((SHELL / "login_summary.bash").read_text()
                            .replace('/opt/sai/shell', str(tmp_path)).replace('/opt/sai/bin/sai', str(summary)))
    env = {k: v for k, v in os.environ.items() if k not in {
        '_SAI_LOGIN_SUMMARY_SHOWN', 'SLURM_JOB_ID', 'SLURM_JOBID',
    }}
    env.update(environment, PYTHONPATH=str(source), HOSTNAME='login-example',
               PATH=environment['PATH'] + ':/usr/bin:/bin', SAI_TEST_NATIVE_CLI=str(command))
    return subprocess.run(['/bin/bash', '--noprofile', '--norc', '-ilc' if login else '-c',
        'gpu() { "$SAI_TEST_NATIVE_CLI" resources local --kind gpu --details --format table; }; '
        'cpu() { "$SAI_TEST_NATIVE_CLI" resources local --kind cpu --details --format table; }; '
        'quota() { printf "LOCAL-QUOTA\\n"; }; source "$1"; printf "SHELL-READY\\n"',
        'bash', str(fragment)], env=env, text=True, capture_output=True, timeout=10)


def test_login_and_manual_status_keep_gpu_positions_and_cpu_bars(tmp_path, native_client):
    _, path, payload = native_client
    payload['sinfo'][0]['gres']['used'] = 'gpu:example:2(IDX:0,2)'
    path.write_text(json.dumps(payload))
    manual = run_status(tmp_path, native_client)
    login = run_status(tmp_path, native_client, login=True)
    assert manual.returncode == login.returncode == 0
    assert not manual.stderr
    for result in (manual, login):
        assert all(name in result.stdout for name in ('node-a', 'node-b', 'node-c'))
        assert '[#][_][#][_]' in result.stdout and '[x][x][x][x]' in result.stdout
        assert '━' in result.stdout and 'Mem GiB' in result.stdout
        assert result.stdout.index('GPU NODE STATUS:') < result.stdout.index('CPU NODE STATUS:') < result.stdout.index('LOCAL-QUOTA')
        assert result.stdout.endswith('SHELL-READY\n')
    assert login.stdout == manual.stdout.replace('SHELL-READY\n', 'ACCOUNT-SUMMARY\nSHELL-READY\n')
    calls = [json.loads(line) for line in Path(native_client[0]['NATIVE_CALL']).read_text().splitlines()]
    assert len(calls) == 4
    assert all(call['argv'] == ['--json', '--local', '--Node'] and not call['sai_token'] for call in calls)


def test_unavailable_native_source_still_reaches_quota_and_shell_without_fake_capacity(tmp_path, native_client):
    _, path, _ = native_client
    path.write_text('{"errors":[{"error":"unavailable"}]}')
    result = run_status(tmp_path, native_client)
    assert result.returncode == 0 and result.stderr
    assert 'GLOBAL' not in result.stdout and '0/0' not in result.stdout
    assert result.stdout.endswith('LOCAL-QUOTA\nSHELL-READY\n')
