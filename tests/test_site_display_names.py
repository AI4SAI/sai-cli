from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.overview import AccountOverview
from sai_cli.overview_view import render_overview
from sai_cli.render import render_table, render_running_estimate_table
from sai_cli.contracts import JobResult, JobCostResult
from sai_cli.sites import SiteConnection, SiteDirectory, render_sites
from test_site_transport import http_endpoint


def test_overview_uses_authoritative_name_in_text_and_retains_site_binding():
    source = Path(__file__).resolve().parents[1] / 'contracts/account-overview/v1/sample.json'
    payload = json.loads(source.read_text())
    payload['site_label'] = '科研计算中心'
    result = AccountOverview.from_payload(payload, site_id=payload['site_id'], request_id='name')
    assert result.as_dict()['site_id'] == payload['site_id']
    assert result.as_dict()['site_label'] == '科研计算中心'
    assert render_overview(result).splitlines()[0] == f"SAI · 科研计算中心 · {payload['user_name']}"
    del payload['site_label']
    unknown = AccountOverview.from_payload(payload, site_id=payload['site_id'], request_id='missing')
    assert '站点名称暂不可用' in render_overview(unknown)
    assert payload['site_id'] not in render_overview(unknown).splitlines()[0]


@pytest.mark.parametrize('label', ['bad\x1b[31mname', {}, 123])
def test_connection_rejects_unsafe_display_names(label):
    value = {'schema_version':'site.connection/v1', 'site_id':'site-a', 'cluster_id':'cluster-a',
             'site_read_base_url':None, 'display_name':label}
    with pytest.raises(ContractError):
        SiteConnection.from_payload(value, site_id='site-a', request_id='bad-name')


def test_human_job_output_uses_name_without_changing_json_scope(job_payload, job_cost_payload):
    jobs = JobResult.from_payload(job_payload, request_id='jobs')
    cost = JobCostResult.from_payload(job_cost_payload, request_id='cost')
    before = deepcopy(jobs.as_dict()), deepcopy(cost.as_dict())
    for output in (render_table(jobs, site_label='Research center'),
                   render_running_estimate_table(cost, site_label='Research center')):
        assert 'Research center' in output
        assert f'Site: {jobs.site_id}' not in output
    assert before == (jobs.as_dict(), cost.as_dict())


def test_site_directory_name_is_primary_and_selector_remains_usable():
    path = Path(__file__).resolve().parents[1]/'contracts/site-directory/v1/sample.json'
    payload=json.loads(path.read_text())
    result=SiteDirectory.from_payload(payload, limit=50, cursor=None, request_id='sites')
    output=render_sites(result)
    assert output.splitlines()[0].startswith('Site') and '--site' in output.splitlines()[0]
    assert output.index(payload['items'][0]['display_name']) < output.index(payload['items'][0]['site_id'])


def test_table_command_fetches_one_exact_site_name_and_json_fetches_none(tmp_path, job_payload):
    connection={'schema_version':'site.connection/v1', 'site_id':job_payload['site_id'],
                'cluster_id':job_payload['cluster_id'], 'site_read_base_url':None, 'display_name':'Research center'}
    def reply(call, count):
        if call['path'].startswith('/v1/account/cli/sites/'):
            return 200,connection
        return 200,job_payload
    with http_endpoint(reply) as (origin,calls):
        env={'SAI_TOKEN':'test-user','XDG_CONFIG_HOME':str(tmp_path/'config')}
        base=['--base-url',origin,'--site',job_payload['site_id'],'jobs','list']
        out,err=StringIO(),StringIO()
        assert main([*base,'--format','table'],environ=env,stdout=out,stderr=err)==0,err.getvalue()
        assert 'Research center' in out.getvalue()
        assert sum('/connection' in c['path'] for c in calls)==1
        calls.clear();out=StringIO()
        assert main([*base,'--format','json'],environ=env,stdout=out,stderr=err)==0,err.getvalue()
        assert not any('/connection' in c['path'] for c in calls)
        assert json.loads(out.getvalue())['site_id']==job_payload['site_id']


def test_default_account_receipts_keep_site_identity_and_show_names():
    from sai_cli.default_account import DefaultAccountState, render_default_account
    from test_default_account import state
    payload=state()
    payload['deliveries'][0]['site_label']='Research center'
    result=DefaultAccountState.from_payload(payload,site_id='site-a',request_id='default')
    assert result.as_dict()['deliveries'][0]['site_id']=='site-a'
    assert 'Research center：已收到应用回执' in render_default_account(result)
    assert 'site-a：' not in render_default_account(result)


def test_overview_site_name_is_shared_with_rich_tui():
    from rich.console import Console
    from sai_cli.overview_view import overview_panel
    path=Path(__file__).resolve().parents[1]/'contracts/account-overview/v1/sample.json'
    payload=json.loads(path.read_text());payload['site_label']='Research center'
    overview=AccountOverview.from_payload(payload,site_id=payload['site_id'],request_id='rich')
    output=StringIO();Console(file=output,width=80,color_system=None).print(overview_panel(overview))
    assert 'Research center' in output.getvalue()
    assert payload['site_id'] not in output.getvalue().splitlines()[0]


@pytest.mark.parametrize('status,code,expected', [
    (404,'site_connection_not_found',0), (503,'site_connection_unavailable',0),
    (401,'authentication_failed',3), (403,'identity_scope_denied',4), (500,'server_error',6),
])
def test_missing_published_name_preserves_data_but_never_hides_authorization_failure(tmp_path,job_payload,status,code,expected):
    def reply(call,count):
        return (status,{'detail':{'code':code}}) if '/connection' in call['path'] else (200,job_payload)
    with http_endpoint(reply) as (origin,calls):
        out,err=StringIO(),StringIO()
        result=main(['jobs','list','--site',job_payload['site_id'],'--base-url',origin,'--format','table'],
                    environ={'SAI_TOKEN':'test-user','XDG_CONFIG_HOME':str(tmp_path/'config')},stdout=out,stderr=err)
        assert result==expected
        if expected==0:
            assert 'Site name unavailable' in out.getvalue()
            assert job_payload['items'][0]['job_id'] in out.getvalue()
        else:
            assert out.getvalue()=='' and code in err.getvalue()
