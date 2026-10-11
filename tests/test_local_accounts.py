"""Native choice discovery is scoped to the actual Unix user, never a Portal login."""
import json
import os
from pathlib import Path
import pwd

import pytest

from test_local_jobs import invoke, native_client, native_job
from test_native_account_tree import tree_client


@pytest.mark.parametrize('prefix', [False, True])
def test_current_uid_accounts_use_shared_bounded_associations_without_portal(tree_client, monkeypatch, prefix):
    env, _, _ = tree_client
    user = pwd.getpwuid(os.geteuid()).pw_name
    env['TREE_ROWS'] = (f'cluster-a|research|{user}|/research/0-{user}/\n'
                        f'cluster-a|project-a|{user}|/research/project-a/0-{user}/\n') * 2
    monkeypatch.setattr('sai_cli.config.resolve_settings', lambda *a: pytest.fail('Portal initialized'))
    words = ['--timeout', '2', 'account', 'local'] if prefix else ['account', 'local', '--timeout', '2']
    code, raw, error = invoke(env, *words)
    assert code == 0 and not error, error
    value = json.loads(raw)
    assert value['accounts'] == ['project-a', 'research']
    assert value['actor'] == {'user': user, 'uid': os.geteuid()}
    assert value['authority'] == 'native' and value['cluster'] == 'cluster-a'
    calls = [json.loads(line) for line in Path(env['TREE_CALLS']).read_text().splitlines()]
    assert len(calls) == 2 and not any(call['unexpected_env'] for call in calls)
    assert calls[1]['argv'] == ['-nP','show','assoc','where','cluster=cluster-a',f'user={user}',
                               'format=Cluster,Account,User,Lineage']
    assert not Path(env['NATIVE_CALL']).exists()


@pytest.mark.parametrize('kind', ['user', 'cluster', 'inconsistent', 'escape', 'failure', 'oversize'])
def test_invalid_or_out_of_scope_discovery_is_not_a_partial_choice_list(tree_client, kind):
    env, _, _ = tree_client
    user = pwd.getpwuid(os.geteuid()).pw_name
    row = f'cluster-a|research|{user}|/research/0-{user}/\n'
    env['TREE_ROWS'] = row
    if kind == 'user':
        env['TREE_ROWS'] += 'cluster-a|private-example|another|/private-example/0-another/\n'
    elif kind == 'cluster':
        env['TREE_ROWS'] += row.replace('cluster-a', 'cluster-b')
    elif kind == 'inconsistent':
        env['TREE_ROWS'] += row.replace('/research/', '/another/research/')
    elif kind == 'escape':
        env['TREE_ROWS'] += row.replace('research|', 'unsafe\x1b[31m|')
    else:
        env['TREE_SCENARIO'] = kind
    code, raw, error = invoke(env, 'account', 'local')
    assert code in (6, 7) and not raw
    assert 'private-example' not in error and 'provider-private-detail' not in error


def test_empty_associations_are_valid_and_connection_overrides_are_rejected(tree_client):
    env, _, _ = tree_client
    env['TREE_ROWS'] = ''
    code, raw, error = invoke(env, 'account', 'local')
    assert code == 0 and json.loads(raw)['accounts'] == [] and not error
    before = Path(env['TREE_CALLS']).read_bytes()
    assert invoke(env, 'account', 'local', '--site', 'another')[0] == 2
    assert Path(env['TREE_CALLS']).read_bytes() == before
