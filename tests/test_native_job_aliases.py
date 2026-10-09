from pathlib import Path
import os
import subprocess

import pytest


PATCH = Path(__file__).resolve().parents[1] / 'site/shell/native_job_aliases.patch'


@pytest.fixture
def native_profile(tmp_path):
    before = tmp_path / 'profile.before'
    after = tmp_path / 'profile.after'
    before.write_text("alias ja='stat_job -A ${GROUP_NAME}'\nalias sqa='stat_job -A ${GROUP_NAME}'\n")
    subprocess.run(['patch', '--batch', '--forward', '-o', str(after), str(before), str(PATCH)],
                   check=True, capture_output=True, text=True)
    subprocess.run(['bash', '-n', str(after)], check=True)
    return after


@pytest.mark.parametrize('alias', ['sqa', 'ja'])
def test_account_queries_use_the_applied_native_account_without_repurposing_unix_group(native_profile, tmp_path, alias):
    script = tmp_path / 'query.bash'
    script.write_text('shopt -s expand_aliases\nsource "$1"\n'
                      'stat_job() { printf "argument=%s\\n" "$@"; }\n'
                      + alias + ' -t R\nprintf "group=%s\\n" "$GROUP_NAME"\n')
    result = subprocess.run(['bash', str(script), str(native_profile)], capture_output=True, text=True,
                            env={**os.environ, 'GROUP_NAME': 'unix-group', '_SAI_LOGIN_ACCOUNT': 'compute-account'})
    assert result.returncode == 0 and not result.stderr
    assert result.stdout.splitlines() == ['argument=-A', 'argument=compute-account', 'argument=--with-subaccounts', 'argument=-t',
                                         'argument=R', 'group=unix-group']


def test_missing_applied_context_cannot_silently_query_the_unix_group_or_all_jobs(native_profile, tmp_path):
    script = tmp_path / 'query.bash'
    script.write_text('shopt -s expand_aliases\nsource "$1"\n'
                      'stat_job() { printf "query executed\\n"; }\nsqa\n')
    result = subprocess.run(['bash', str(script), str(native_profile)], capture_output=True, text=True,
                            env={**os.environ, 'GROUP_NAME': 'unix-group', '_SAI_LOGIN_ACCOUNT': ''})
    assert result.returncode != 0 and not result.stdout
    assert 'No applied Slurm account' in result.stderr
