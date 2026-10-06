from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.managed_runs import MyManagedRunList
from test_cli_integration import _env, _server


def sample():
    return json.loads((Path(__file__).resolve().parents[1] / 'contracts/managed-my-runs/v1/sample.json').read_text())


def parse(value, *, cursor=None, limit=50):
    return MyManagedRunList.from_payload(value, site_id='site-a', limit=limit, cursor=cursor, request_id='my-work')


def test_my_work_rows_keep_server_context_and_drop_unmodeled_fields():
    value = sample()
    for kind in ('personal', 'org'):
        value['items'].append({**value['items'][0], 'run_ref': f'run-{kind}', 'workspace_key': f'{kind}:account-example'})
    original = deepcopy(value)
    value['wallet'] = {'secret': 'private'}
    for row in value['items']:
        row.update(script='private command', environment={'secret': 'private'})
    result = parse(value)
    assert result.as_dict() == original
    result.as_dict()['items'].clear()
    assert len(result.values['items']) == 3
    value.update(has_more=True, next_cursor='run-org')
    assert parse(value).values['next_cursor'] == 'run-org'
    with pytest.raises(ContractError):
        parse(value, cursor='run-org')
    with pytest.raises(ContractError):
        parse(value, limit=2)


@pytest.mark.parametrize('change', [
    {'schema_version': 'compute.runs/v1'}, {'site_id': 'site-other'}, {'source': 'squeue'},
    {'queried_at': 'not-a-time'}, {'has_more': True}, {'next_cursor': 'run-other'}, {'items': {}},
])
def test_my_work_rejects_wrong_context_or_incomplete_pages(change):
    with pytest.raises(ContractError):
        parse({**sample(), **change})


@pytest.mark.parametrize('change', [
    {'workspace_key': 'all:others'}, {'workspace_label': '\x1b[2J'}, {'organization_label': '\nprivate'},
    {'workspace_label': ''}, {'workspace_key': None}, {'state_revision': True},
])
def test_my_work_nested_context_is_allowlisted_and_safe(change):
    value = sample()
    value['items'][0].update(change)
    with pytest.raises(ContractError):
        parse(value)


@pytest.mark.parametrize('prefix', [True, False])
@pytest.mark.parametrize('output_format', ['json', 'table'])
def test_recent_command_reads_one_identity_bound_site_page(tmp_path, prefix, output_format):
    value = sample()
    with _server(value) as (origin, server):
        connection = ['--base-url', origin, '--site', 'site-a']
        args = ['runs', 'recent', '--limit', '3', '--cursor', 'run-older', '--format', output_format]
        stdout, stderr = StringIO(), StringIO()
        code = main(connection + args if prefix else args + connection, environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 0 and stderr.getvalue() == ''
    assert json.loads(stdout.getvalue()) == value if output_format == 'json' else 'Example project' in stdout.getvalue()
    assert len(server.requests) == 1
    request = server.requests[0]
    assert request['path'] == '/v1/compute/cli/my-runs'
    assert request['query'] == {'site_id': ['site-a'], 'limit': ['3'], 'cursor': ['run-older']}
    assert request['authorization'] == 'Bearer test-bearer-token' and request['capability'] is None


@pytest.mark.parametrize('arguments', [['--workspace-key', 'project:other'], ['--user', 'other'], ['--limit', '101'], ['--cursor', '../other']])
def test_recent_never_accepts_an_actor_or_unbounded_request(tmp_path, arguments):
    with _server(sample()) as (origin, server):
        stdout, stderr = StringIO(), StringIO()
        args = ['runs', 'recent', '--site', 'site-a', '--base-url', origin, *arguments]
        if arguments[0] in {'--workspace-key', '--user'}:
            with pytest.raises(SystemExit) as error:
                main(args, environ=_env(tmp_path), stdout=stdout, stderr=stderr)
            code = error.value.code
        else:
            code = main(args, environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 2 and stdout.getvalue() == '' and not server.requests


@pytest.mark.parametrize('fault', [None, 'wrong_reference', 'wrong_workspace', 'truncated'])
def test_exact_work_lookup_repeats_the_reference_and_workspace_boundary(fault):
    from types import SimpleNamespace
    from sai_cli.auth import TokenLease
    from sai_cli.client import PortalClient
    from sai_cli.transport import JsonTransport

    reference = '12345678-abcd-4321-abcd-123456789012'
    value = sample()
    value['items'][0]['run_ref'] = reference
    if fault == 'wrong_reference': value['items'][0]['run_ref'] = 'another-run'
    elif fault == 'wrong_workspace': value['items'][0]['workspace_key'] = 'org:other'
    elif fault == 'truncated': value.update(has_more=True, next_cursor=reference)
    with _server(value) as (origin, server):
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=3),
            token_provider=SimpleNamespace(get=lambda: TokenLease('test-bearer-token', None, 'environment')))
        def read():
            return client.list_my_managed_runs(site_id='site-a', run_refs=(reference,),
                workspace_key='project:project-example', limit=100)
        if fault:
            with pytest.raises(ContractError): read()
        else:
            assert read().values['items'][0]['run_ref'] == reference
    assert len(server.requests) == 1
    assert server.requests[0]['query'] == {'site_id': ['site-a'], 'limit': ['100'],
        'run_refs': [reference], 'workspace_key': ['project:project-example']}
