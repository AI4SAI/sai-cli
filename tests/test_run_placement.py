from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import main
from sai_cli.errors import ConfigError, ContractError
from sai_cli.run_placement import ManagedRunPlacement, render_run_placement
from test_cli_integration import _env, _server
from test_managed_runs_contract import parse as parse_run
from test_site_placement import current_placement


def sample(name="allocated"):
    return json.loads((Path(__file__).resolve().parents[1]/"contracts/managed-run-placement/v1"/f"{name}.sample.json").read_text())


def parse(data):
    return ManagedRunPlacement.from_payload(data,run_ref="run-example-1",workspace_key="project:project-example",site_id="site-a",request_id="run-placement")


def current_sample(name="allocated"):
    value = sample(name)
    value["placement"] = current_placement(value["placement"])
    if value["execution"] is not None:
        now = datetime.now(timezone.utc)
        for key, seconds in (("submit_time", -120), ("start_time", -60)):
            stamp = (now + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
            value["execution"][key] = value["placement"]["allocation"]["job"][key] = stamp
    return value


@pytest.mark.parametrize("name",["allocated","unmapped","not-allocated"])
def test_run_placement_reuses_existing_nested_allowlist(name):
    expected=sample(name);data=deepcopy(expected)
    rows=[data,data["placement"],data["placement"]["allocation"],data["placement"]["allocation"]["job"]]
    if data['execution']:rows.append(data['execution'])
    if data['placement']['nodes']:rows.append(data['placement']['nodes'][0])
    for row in rows:row['secret']='/sensitive-fixture'
    value=parse(data)
    assert value.as_dict()==expected
    assert 'sensitive-fixture' not in render_run_placement(value)
    assert value.placement.allocation.site_id=='site-a'


@pytest.mark.parametrize("path,value",[
    (("schema_version",),"jobs.placement/v1"),(("run_ref",),"run-other"),(("site_id",),"site-b"),(("workspace_key",),"project:other"),
    (("queried_at",),"2030-02-30T00:00:00Z"),(("queried_at",),"2030-01-01T00:00:02Z\n"),
    (("execution",),None),(("execution","sluid"),"s0000000000001\n"),(("execution","restart_count"),True),
    (("execution","submit_time"),"2029-12-31T23:30:01Z"),(("execution","start_time"),"2030-01-01T00:00:00.000001Z"),
    (("execution","restart_count"),1),(("execution","resize_time"),"invalid"),
    (("placement","allocation","site_id"),"site-b"),(("placement","allocation","freshness","source"),"squeue"),
    (("placement","allocation","job","array_task_id"),"0"),
    (("placement","allocation","scope_type"),"org_account"),(("placement","allocation","subject","slurm_user"),None),(("placement","allocation","subject","slurm_user"),"other"),
    (("placement","allocation","job","start_time"),None),(("placement","allocation","restart_count"),None),
    (("placement","nodes",0,"name"),"node-other"),(("placement","nodes",0,"registration","asset_ref"),"unsafe\x1b"),
    (("placement","inventory","expires_at"),"2029-12-31T00:00:00Z"),
])
def test_run_placement_rejects_scope_expansion_unknown_execution_and_nested_conflicts(path,value):
    data=sample();row=data
    for key in path[:-1]:row=row[key]
    row[path[-1]]=value
    with pytest.raises(ContractError):parse(data)


def test_run_placement_requires_wrapper_fields_and_preserves_same_instant_fraction():
    for path in [(),('execution',)]:
        original=sample();row=original
        for key in path:row=row[key]
        for field in row:
            data=sample();target=data
            for key in path:target=target[key]
            del target[field]
            with pytest.raises(ContractError):parse(data)
    data=sample('not-allocated');data['execution']=sample()['execution']
    with pytest.raises(ContractError):parse(data)
    data=sample();data['execution']['submit_time']='2029-12-31T23:30:00.000000Z'
    assert parse(data).values['execution']['submit_time']==data['execution']['submit_time']


@pytest.mark.parametrize('prefix',[True,False])
@pytest.mark.parametrize('format',['json','table'])
def test_runs_placement_uses_exact_run_and_scope_over_http(tmp_path,prefix,format):
    body=current_sample()
    with _server(body) as (origin,server):
        connection=['--base-url',origin,'--site','site-a']
        command=['runs','placement','run-example-1','--workspace-key','project:project-example','--format',format]
        out,err=StringIO(),StringIO();code=main(connection+command if prefix else command+connection,environ=_env(tmp_path),stdout=out,stderr=err)
    assert code==0,err.getvalue()
    assert len(server.requests)==1
    assert server.requests[0]['path']=='/v1/compute/cli/runs/run-example-1/placement'
    assert server.requests[0]['query']=={'workspace_key':['project:project-example'],'site_id':['site-a']}
    assert server.requests[0]['capability'] is None
    if format=='json':assert json.loads(out.getvalue())==body
    else:assert 'Rack A, U12, height 4U' in out.getvalue() and 'Runtime SLUID:' in out.getvalue()


@pytest.mark.parametrize('status,code',[(403,'run_placement_not_enabled'),(403,'run_read_denied'),(409,'run_execution_changed'),(503,'run_placement_unavailable')])
def test_run_placement_http_failure_never_falls_back_to_native_job(tmp_path,status,code):
    with _server({'detail':{'code':code,'message':'Unavailable','raw':'sensitive-fixture'}},status=status) as (origin,server):
        out,err=StringIO(),StringIO();result=main(['runs','placement','run-example-1','--workspace-key','project:project-example','--site','site-a','--base-url',origin],environ=_env(tmp_path),stdout=out,stderr=err)
    assert result!=0 and out.getvalue()=='' and len(server.requests)==1
    assert 'sensitive-fixture' not in err.getvalue()


def test_run_placement_web_url_never_carries_indices_or_metrics():
    detail=parse_run('detail');url=urlsplit(detail.web_url('https://portal.example',placement=True))
    assert parse_qs(url.fragment.split('?',1)[1])=={'run_ref':['run-example-1'],'view':['placement']}
    for extra in ({'cost':True},{'stats':True},{'artifact_ref':'artifact-x'},{'artifact_page':parse_run('artifacts')},{'placement':'true'}):
        with pytest.raises(ConfigError):detail.web_url('https://portal.example',**{'placement':True,**extra})
