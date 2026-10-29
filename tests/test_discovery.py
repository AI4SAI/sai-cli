"""Discovery is offline and accurately describes real callable operations."""
from io import StringIO
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from sai_cli.cli import build_parser, main
from sai_cli.discovery import describe
from test_default_account import state, acceptance
from test_site_transport import http_endpoint
from test_local_jobs import native_client, native_job


def invoke(words, env=None):
    out, err = StringIO(), StringIO()
    code = main(words, environ=env or {}, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def operation(*words):
    return describe(build_parser(), list(words))["operations"][0]


def test_discovery_is_independent_of_config_auth_native_commands_and_ui(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('discovery attempted runtime initialization')
    monkeypatch.setattr('sai_cli.config.resolve_settings', forbidden)
    monkeypatch.setattr('sai_cli.cli._build_transport', forbidden)
    monkeypatch.setattr('sai_cli.native_process.read_native_json', forbidden)
    env={'PATH':'', 'SAI_MANAGED_LOGIN_NODE':'1', 'SAI_CONFIG':str(tmp_path/'absent'), 'SAI_TOKEN':'private-example-token'}
    code, output, error=invoke(['describe'],env)
    assert code==0 and not error and 'private-example-token' not in output and str(tmp_path) not in output
    payload=json.loads(output)
    assert payload['schema_version']=='cli.describe/v1' and payload['authorization_checked'] is False
    assert payload['detailed'] is False
    commands={tuple(row['command']) for row in payload['operations']}
    assert len(commands)==39 and {('configure',),('sites',),('jobs','local'),('jobs','charges'),('runs','download'),('account','local'),('account','set-default'),('describe',),('skill',),('invitations','accept')}<=commands
    assert not any('parameters' in row for row in payload['operations'])
    for words in commands:
        exact=describe(build_parser(),list(words))
        assert exact['detailed'] and len(exact['operations'])==1
        names=[p['name'] for p in exact['operations'][0]['parameters']]
        assert len(names)==len(set(names))
        assert '_operation' not in names
        json.dumps(exact)


def test_types_choices_required_flags_and_exclusive_selectors_come_from_parser():
    local=operation('jobs','local')
    assert local['source']=='native' and local['required_scopes']==[] and local['native_executables']==[]
    assert any(row.get('executables')==['scontrol'] for row in local['conditional_requirements'])
    fields={row['name']:row for row in local['parameters']}
    assert fields['limit']['type']=='integer'
    assert fields['with_subaccounts']['type']=='boolean' and fields['with_subaccounts']['arity']==0
    assert fields['accounts']['flags']==['-A','--account','--accounts']
    assert not {'config','site','cluster','base_url'}&fields.keys()
    remote=operation('jobs','list')
    fields={row['name']:row for row in remote['parameters']}
    assert fields['scope']['choices']==['self','personal-account','org-account','project-account']
    assert remote['exclusive_parameters']==[{'parameters':['account','account_id','workspace_key'],'required':False}]
    assert {row['name'] for row in operation('account','set-default')['parameters'] if row['required']}=={'account_id','if_current','request_id'}
    for words in [('status',),('runs','read'),('account','defaults'),('storage','native-quota')]:
        assert 'cluster' not in {row['name'] for row in operation(*words)['parameters']}


def test_effects_scope_minima_and_readback_do_not_invent_authority():
    assert operation('tui')['interaction']=='terminal'
    assert operation('auth','login')['interaction']=='browser_consent'
    assert operation('auth','logout')['effect']=='session_write'
    assert operation('tui')['effect']=='session_write'
    assert operation('tui')['required_scopes']==[]
    assert operation('auth','status')['required_scopes']==[]
    assert operation('runs','download')['effect']=='local_file_write'
    assert operation('runs','cost')['required_scopes']==['sai.billing.read']
    assert not operation('sites')['site_required'] and not operation('sites')['site_option']
    assert operation('sites')['required_scopes']==['sai.compute.read']
    assert operation('runs','read')['required_scopes']==['sai.compute.read']
    assert operation('storage','native-quota')['required_scopes']==['sai.storage.read']
    write=operation('account','set-default')
    assert write['effect']=='business_write' and write['required_scopes']==['sai.compute.defaults.write']
    assert write['site_required'] is False and write['site_option'] is False and write['readback']==['account','defaults']
    assert not {'site','cluster'}&{row['name'] for row in write['parameters']}
    assert any('accepted does not mean applied' in note for note in write['notes'])
    assert operation('jobs','cost')['conditional_requirements']==[{'when':'job_id is supplied','scopes':['sai.compute.read']}]
    invitation = operation('invitations', 'accept')
    assert invitation['effect'] == 'read' and invitation['required_scopes'] == ['sai.collaboration.invitations.read']
    assert invitation['conditional_requirements'] == [{'when': '--apply is supplied', 'effect': 'business_write',
                                                      'scopes': ['sai.collaboration.invitations.accept']}]
    assert not next(row for row in invitation['parameters'] if row['name'] == 'apply')['default']


def test_group_filter_unknown_path_and_table_output():
    group=describe(build_parser(),['jobs'])
    assert group['detailed'] is False and len(group['operations'])==7
    code,output,error=invoke(['describe','jobs','local','--format','table'])
    assert code==0 and not error and '-A, --account, --accounts' in output
    code,output,error=invoke(['describe','jobs','cancel'])
    assert code==2 and not output and json.loads(error)['error']['code']=='command_not_found'
    assert 'cancel' not in error


def test_native_operation_discovered_then_called_without_portal(native_client):
    env,_,_=native_client
    description=operation('jobs','local')
    code,output,error=invoke(description['command'],env)
    assert code==0 and not error
    result=json.loads(output)
    assert result['authority']=='native' and result['source']=='squeue'
    assert not json.loads(Path(env['NATIVE_CALL']).read_text())['sai_token_present']


def test_agent_uses_discovered_write_and_reads_accepted_state_over_http(tmp_path,monkeypatch):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    current=state()
    def reply(call,number):
        assert call['bearer']=='Bearer test-user' and call['capability'] is None
        if call['method']=='PUT':
            assert call['idempotency_key']=='agent-example-request'
            current['default_account_id']='account-research'
            current['effective_account_id']='account-research'
            return 200,acceptance(call)
        assert call['method']=='GET' and urlsplit(call['path']).path=='/v1/account/cli/defaults'
        return 200,current
    with http_endpoint(reply) as (origin,calls):
        env={'SAI_API_BASE_URL':origin,'SAI_SITE_ID':'site-a','SAI_TOKEN':'test-user',
             'XDG_CONFIG_HOME':str(tmp_path/'config')}
        write=operation('account','set-default')
        code,output,error=invoke(write['readback'],env)
        assert code==0 and not error
        before=json.loads(output)
        assert any(row['id']=='account-research' for row in before['choices'])
        expected=before['default_account_id'] or 'auto'
        arguments=[*write['command'],'account-research','--if-current',expected,'--request-id','agent-example-request']
        code,output,error=invoke(arguments,env)
        assert code==0 and not error
        assert json.loads(output)['state']=='accepted'
        code,output,error=invoke(write['readback'],env)
        assert code==0 and not error and json.loads(output)['default_account_id']=='account-research'
        assert [call['method'] for call in calls]==['GET','PUT','GET']


def test_optional_site_is_distinct_from_required_site():
    for words in [('tui',),('auth','login'),('auth','status'),('auth','logout')]:
        info=operation(*words)
        assert not info['site_required'] and info['site_option']
        assert 'site' in {row['name'] for row in info['parameters']}
        assert build_parser().parse_args([*words,'--site','site-a']).site=='site-a'
    assert operation('account','defaults')['site_required']
    assert 'revoked result' in operation('auth','logout')['notes'][0]
