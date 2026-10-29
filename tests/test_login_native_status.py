import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from test_local_resources import native_client


FRAGMENT = Path(__file__).resolve().parents[1] / "site/shell/status.bash"


def run_status(tmp_path, native_client, arguments):
    environment, _, _ = native_client
    command = tmp_path / "sai"
    source = Path(__file__).resolve().parents[1] / "src"
    command.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m sai_cli "$@"\n')
    command.chmod(0o755)
    fragment = tmp_path / "status.bash"
    fragment.write_text(FRAGMENT.read_text().replace('/opt/sai/bin/sai', str(command)))
    return subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c',
        'gpu() { printf "GPU-DETAIL\\n"; }; cpu() { printf "CPU-DETAIL\\n"; }; '
        'quota() { printf "LOCAL-QUOTA\\n"; }; source "$1" "${@:2}"; printf "SHELL-READY\\n"',
        'bash', str(fragment), *arguments], env={**os.environ, **environment, 'PYTHONPATH': str(source)},
        text=True, capture_output=True, timeout=10)


def test_login_summary_uses_one_native_observation_and_preserves_local_quota(tmp_path, native_client):
    result = run_status(tmp_path, native_client, ['--summary'])
    assert result.returncode == 0 and not result.stderr
    assert 'GPU-DETAIL' not in result.stdout and 'CPU-DETAIL' not in result.stdout
    assert 'GPU' in result.stdout and 'CPU' in result.stdout and 'Mem GiB' in result.stdout
    assert 'Max free' in result.stdout and '/node' in result.stdout
    assert result.stdout.endswith('LOCAL-QUOTA\nSHELL-READY\n')
    calls = [json.loads(line) for line in Path(native_client[0]['NATIVE_CALL']).read_text().splitlines()]
    assert len(calls) == 1 and calls[0]['argv'] == ['--json', '--local', '--Node']
    assert not calls[0]['sai_token']


def test_manual_status_keeps_existing_node_helpers_and_quota(tmp_path, native_client):
    result = run_status(tmp_path, native_client, [])
    assert result.returncode == 0 and not result.stderr
    assert result.stdout.index('GPU-DETAIL') < result.stdout.index('CPU-DETAIL') < result.stdout.index('LOCAL-QUOTA')
    assert not Path(native_client[0]['NATIVE_CALL']).exists()


def test_unavailable_native_source_still_reaches_quota_and_shell_without_fake_capacity(tmp_path, native_client):
    _, path, _ = native_client
    path.write_text('{"errors":[{"error":"unavailable"}]}')
    result = run_status(tmp_path, native_client, ['--summary'])
    assert result.returncode == 0 and result.stderr
    assert 'TOTAL' not in result.stdout and '0/0' not in result.stdout
    assert result.stdout.endswith('LOCAL-QUOTA\nSHELL-READY\n')
