"""Keyboard interaction with real bounded native processes and authorized HTTP."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from textual.widgets import DataTable, Select, Static, Tabs

from sai_cli.cli import build_parser
from sai_cli.errors import AuthenticationError, ContractError
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries, Read
from test_local_jobs import native_client, native_job
from test_native_topology import topology_client as job_client
from test_local_resources import native_client as resource_client
from test_overview import sample
from test_site_transport import http_endpoint


async def loaded(app, pilot):
    for _ in range(100):
        await pilot.pause(.02)
        if not app._reading:
            return
    pytest.fail('read did not finish')


@pytest.mark.parametrize('width', [40, 80, 120])
def test_job_selection_refresh_details_and_exit_without_portal(job_client, monkeypatch, width):
    env, path, payload = job_client
    def forbidden(*args, **kwargs):
        pytest.fail('local terminal queried Portal/config/auth')
    monkeypatch.setattr('sai_cli.config.resolve_settings', forbidden)
    second = deepcopy(payload['jobs'][0]);second.update(job_id=43, name='second-job')
    payload['jobs'].append(second);path.write_text(json.dumps(payload))
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']), env))
        async with app.run_test(size=(width,24)) as pilot:
            await loaded(app,pilot)
            assert app.query_one('#job-table',DataTable).row_count == 2
            assert app.query_one('#job-table').has_focus
            await pilot.press('down','enter');await loaded(app,pilot)
            assert app.query_one('#detail').display
            assert 'second-job' in app.export_screenshot()
            await pilot.press('escape')
            assert not app.query_one('#detail').display
            await pilot.press('r');await loaded(app,pilot)
            assert app.query_one('#job-table',DataTable).cursor_row == 1
            await pilot.press('q')
        call=json.loads(Path(env['NATIVE_CALL']).read_text())
        assert call['argv'][:3] == ['--json','--local',f"--user={payload['jobs'][0]['user_name']}"]
        assert not call['sai_token_present']
    asyncio.run(run())


def test_partition_choice_uses_one_native_observation_and_preserves_indices(resource_client, monkeypatch):
    env,path,payload=resource_client
    payload['sinfo'][0]['gres']['used']='gpu:example:2(IDX:1,3)'
    path.write_text(json.dumps(payload))
    monkeypatch.setattr('sai_cli.config.resolve_settings',lambda *a:pytest.fail('Portal invoked'))
    async def run():
        app=QueryApp(Queries(build_parser().parse_args(['tui']),env))
        async with app.run_test(size=(100,30)) as pilot:
            await loaded(app,pilot)
            assert app.view=='gpu'
            assert app.snapshot.values['nodes'][0]['gpu']['allocated_indices']==[1,3]
            app.query_one('#selection',Select).value='gpu-new'
            await pilot.pause()
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines())==1
            assert app.selection=='gpu-new'
            await pilot.press('3');await loaded(app,pilot)
            assert app.view=='cpu'
            assert app.snapshot.values['filters']['kind']=='cpu'
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines())==2
            await pilot.resize_terminal(40,20)
            await pilot.pause()
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines())==2
    asyncio.run(run())


def test_slow_native_read_coalesces_refresh_and_never_overwrites_new_view(job_client):
    queries=Queries(build_parser().parse_args(['tui']),job_client[0]);original=queries.read
    started,release=asyncio.Event(),asyncio.Event();calls=[]
    async def read(request):
        calls.append(request.view)
        if len(calls)==1:
            started.set();await asyncio.wait_for(release.wait(),3)
        if request.view=='accounts':raise AuthenticationError('private test marker')
        return await original(request)
    queries.read=read
    async def run():
        app=QueryApp(queries)
        async with app.run_test(size=(80,24)) as pilot:
            for _ in range(30):
                await pilot.pause(.01)
                if started.is_set():break
            assert started.is_set()
            app.action_refresh();app.action_refresh()
            app.query_one(Tabs).active='account'
            await pilot.pause(.05)
            assert app.view=='account' and app.snapshot is None
            release.set();await loaded(app,pilot)
            assert calls==['jobs','accounts']
            assert 'sai auth login' in str(app.query_one('#notice',Static).render())
            assert 'private test marker' not in str(app.query_one('#notice',Static).render())
            assert app.snapshot is None
    asyncio.run(run())


def test_account_names_refresh_and_failure_clear_old_private_data(tmp_path,monkeypatch):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    from test_default_account import state
    fail=[False]
    directory_denied=[False]
    def reply(call,_):
        assert call['method']=='GET' and call['bearer']=='Bearer test-user'
        if '/defaults?' in call['path']:
            return (403, {'detail':{'code':'scope_denied','message':'Denied'}}) if directory_denied[0] else (200,state())
        if fail[0]:return 403,{'detail':{'code':'scope_denied','message':'Denied'}}
        value=sample()
        if 'slurm_account_name=' in call['path']:
            from urllib.parse import parse_qs,urlsplit
            name=parse_qs(urlsplit(call['path']).query)['slurm_account_name'][0]
            value['context'].update(slurm_account=name,canonical_account=name,label=name)
        return 200,value
    with http_endpoint(reply) as (origin,calls):
        args=build_parser().parse_args(['tui','--site','site-a','--base-url',origin])
        queries=Queries(args,{'PATH':'/not-present','XDG_CONFIG_HOME':str(tmp_path),'SAI_TOKEN':'test-user'})
        async def run():
            app=QueryApp(queries)
            async with app.run_test(size=(60,24)) as pilot:
                await loaded(app,pilot)
                assert len(calls)==2 and app.snapshot is not None
                assert not app.query('#choose')
                app.query_one('#selection',Select).value='org-research'
                await loaded(app,pilot)
                assert len(calls)==4
                fail[0]=True
                await pilot.press('r');await loaded(app,pilot)
                assert app.snapshot is None
                assert not str(app.query_one('#content',Static).render())
                assert not app.query_one(Select).disabled
                fail[0]=False
                app.query_one(Select).value='personal-alice'
                await loaded(app,pilot)
                assert app.selection=='personal-alice' and app.snapshot is not None
                directory_denied[0]=True
                await pilot.press('r');await loaded(app,pilot)
                assert app.snapshot is None and app.query_one(Select).disabled
                assert len(app._options)==1
                assert all(call['method']=='GET' for call in calls)
        asyncio.run(run())


def test_selected_native_cost_reauthorizes_over_real_http_and_rejects_reused_job(job_cost_payload, tmp_path, monkeypatch):
    from sai_cli.contracts import JobItem
    from sai_cli.errors import ForbiddenError, ConfigError
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    denied=[False]
    def reply(call,_):
        assert call['method']=='GET' and '/jobs/12345?' in call['path']
        assert 'include_estimate=true' in call['path']
        return (403,{'detail':{'code':'job_cost_read_denied'}}) if denied[0] else (200,job_cost_payload)
    with http_endpoint(reply) as (origin,calls):
        args=build_parser().parse_args(['tui','--site','site-a','--cluster','cluster-a','--base-url',origin])
        queries=Queries(args,{'PATH':'/not-present','XDG_CONFIG_HOME':str(tmp_path),'SAI_TOKEN':'test-user'})
        item=JobItem.from_payload(job_cost_payload['items'][0],request_id='native')
        request=Read('cost','mine',{'cluster':'cluster-a','item':item})
        assert asyncio.run(queries.read(request)).estimate.values['gross_cny']=='2.00000000'
        # A reused native job number must not acquire the predecessor's price.
        changed=JobItem({**item.values,'submit_time':'2026-08-01T00:00:00Z'})
        with pytest.raises(ContractError):asyncio.run(queries.read(Read('cost','mine',{'cluster':'cluster-a','item':changed})))
        denied[0]=True
        with pytest.raises(ForbiddenError):asyncio.run(queries.read(request))
        count=len(calls)
        with pytest.raises(ConfigError):asyncio.run(queries.read(Read('cost','mine',{'cluster':'other-cluster','item':item})))
        assert len(calls)==count


def test_cost_keyboard_selection_clears_previous_amount_on_rejection(job_client,job_cost_payload):
    from sai_cli.contracts import JobCostResult
    queries=Queries(build_parser().parse_args(['tui']),job_client[0]);original=queries.read
    result=JobCostResult.from_payload(job_cost_payload,request_id='test')
    calls=[]
    async def read(request):
        calls.append(request)
        if request.view=='cost':
            if len([r for r in calls if r.view=='cost']) > 1:
                from sai_cli.errors import ForbiddenError
                raise ForbiddenError('Estimate denied')
            return result
        return await original(request)
    queries.read=read
    async def run():
        app=QueryApp(queries)
        async with app.run_test(size=(40,24)) as pilot:
            await loaded(app,pilot)
            await pilot.press('c');await loaded(app,pilot)
            assert calls[-1].job['item'].canonical_id=='42'
            assert app.query_one('#detail').display
            await pilot.press('c');await loaded(app,pilot)
            assert not app.query_one('#detail').display
            assert not str(app.query_one('#detail-content',Static).render())
    asyncio.run(run())


def test_immediate_result_is_not_discarded_by_delayed_widget_events(job_client):
    queries=Queries(build_parser().parse_args(['tui']),job_client[0])
    snapshot=asyncio.run(queries.read(Read('jobs','mine')))
    async def immediate(request):return snapshot
    queries.read=immediate
    async def run():
        app=QueryApp(queries)
        async with app.run_test(size=(80,24)) as pilot:
            await loaded(app,pilot)
            await pilot.pause(.1)
            assert app.snapshot is snapshot
            assert app.query_one('#job-table',DataTable).row_count==1
            assert app.selection=='mine' and not app._reading
    asyncio.run(run())


def test_quit_cancels_the_query_process_and_native_child(tmp_path):
    import os
    import sys
    import time
    binary=tmp_path/'squeue'; marker=tmp_path/'pid'
    binary.write_text(f'#!{sys.executable}\nimport os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n')
    binary.chmod(0o755)
    queries=Queries(build_parser().parse_args(['tui']),{'PATH':str(tmp_path)})
    timing=[]
    async def run():
        app=QueryApp(queries)
        async with app.run_test(size=(60,20)) as pilot:
            for _ in range(60):
                await pilot.pause(.02)
                if marker.exists():break
            assert marker.exists()
            timing.append(time.monotonic())
            await pilot.press('q')
    asyncio.run(run())
    assert time.monotonic()-timing[0]<1.5
    status=Path('/proc')/marker.read_text()/'status'
    assert not status.exists() or '\nState:\tZ' in status.read_text()


@pytest.mark.parametrize('repeat',[False,True])
def test_leaving_job_clears_pending_cost_errors_and_loading(job_client,repeat):
    from sai_cli.errors import ForbiddenError
    env,path,payload=job_client
    second=deepcopy(payload['jobs'][0]);second['job_id']=43
    payload['jobs'].append(second);path.write_text(json.dumps(payload))
    queries=Queries(build_parser().parse_args(['tui']),env);original=queries.read
    started,release=asyncio.Event(),asyncio.Event()
    async def read(request):
        if request.view=='cost':
            started.set();await release.wait();raise ForbiddenError('old row error')
        return await original(request)
    queries.read=read
    async def run():
        app=QueryApp(queries)
        async with app.run_test(size=(80,24)) as pilot:
            await loaded(app,pilot)
            await pilot.press('c');await asyncio.wait_for(started.wait(),2)
            if repeat:await pilot.press('c')
            await pilot.press('down')
            assert not str(app.query_one('#notice',Static).render())
            release.set();await loaded(app,pilot)
            assert not str(app.query_one('#notice',Static).render())
            assert app._pending is None and not app.query_one('#detail').display
    asyncio.run(run())
