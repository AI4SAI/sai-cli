import asyncio
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip('textual')
from textual.widgets import Button, DataTable, TabbedContent

from sai_cli.client import JobQuery
from sai_cli.run_placement import ManagedRunPlacement
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.tui import Workbench
from test_managed_runs_contract import sample as run_sample
from test_managed_workspaces import sample as project_sample
from test_run_placement import sample, current_sample
from test_site_transport import http_endpoint
from test_tui import catalog, settled
from test_tui_managed_runs import click, client_for, command, details


def responder(state):
    def reply(call,_):
        path=urlsplit(call['path']).path
        if path.endswith('/placement'):
            if state.get('started'):
                state['started'].set();assert state['release'].wait(10)
            if state.get('status'):return state['status'],{'detail':{'code':state['code'],'message':'Unavailable'}}
            return 200,state.get('body',current_sample(state.get('sample','allocated')))
        if path.endswith('/logs'):return 200,run_sample('log')
        if path.endswith('/artifacts'):return 200,run_sample('artifacts')
        if path.endswith('/runs'):return 200,run_sample('list')
        if path.endswith('/workspaces'):return 200,project_sample()
        if path.endswith('resource-catalog'):return 200,catalog()
        return 200,run_sample('detail')
    return reply


async def open_detail(app,pilot):
    await settled(app,pilot);app.query_one('#tasks-table',DataTable).focus()
    await pilot.press('enter');await settled(app,pilot)


def app_for(origin,language='en-US'):
    return Workbench(client_for(origin),JobQuery(site_id='site-a'),initial_view='tasks',language=language,
                     tasks_workspace_key='project:project-example',refresh_seconds=999)


@pytest.mark.parametrize('language',['zh-CN','en-US'])
def test_run_location_is_explicit_readable_and_reuses_task_actions(tmp_path,monkeypatch,language):
    monkeypatch.delenv('NO_COLOR',raising=False);state={}
    async def scenario(origin,calls):
        app=app_for(origin,language);opened=[];app.open_url=opened.append
        async with app.run_test(size=(40,18)) as pilot:
            await open_detail(app,pilot);metadata=app.results['tasks']
            assert not any('/placement?' in call['path'] for call in calls)
            await click(app,pilot,'#task-placement')
            assert isinstance(app.task_placement,ManagedRunPlacement) and app.results['tasks'] is metadata
            assert not app._presentation().automatic_refresh and not app.check_action('pause',())
            before=len(calls);app._tick();await pilot.press('f6');await pilot.pause(.04);assert len(calls)==before
            for width,height in ((40,18),(60,24),(100,32)):
                await pilot.resize_terminal(width,height);await pilot.pause(.05)
                for name in ('detail','stdout','stderr','files','cost','stats','placement'):
                    area=app.query_one('#task-'+name).region
                    assert 0<=area.x<area.right<=width and area.bottom<height,(name,area)
                assert app.query_one('#task-evidence-actions').region.height==(2 if width<60 else 1)
                assert app.query_one('#details-scroll').region.height>=max(6,height//3)
                visible='\n'.join(strip.text for strip in app.screen._compositor.render_strips())
                assert 'Rack A' in visible and 'U12' in visible
                app.save_screenshot(str(tmp_path/f'run-placement-{language}-{width}x{height}.svg'))
            await pilot.press('w');await pilot.pause(.04)
            assert parse_qs(urlsplit(opened[-1]).fragment.split('?',1)[1])=={'run_ref':['run-example-1'],'view':['placement']}
            await click(app,pilot,'#task-files')
            assert app.task_placement is None and not app.query_one('#task-placement').display
            await command(app,pilot,app.t('command_placement'))
            assert app.task_mode=='placement' and 'Rack A' in details(app)
            for name in ('unmapped','not-allocated'):
                state['sample']=name;await pilot.press('f5');await settled(app,pilot)
                assert 'Rack A' not in details(app)
                assert app.task_placement.placement.allocation.allocation_status==('not_allocated' if name=='not-allocated' else 'allocated')
            await click(app,pilot,'#task-detail');assert app.task_placement is None and app._presentation().automatic_refresh
    with http_endpoint(responder(state)) as (origin,calls):asyncio.run(scenario(origin,calls))


@pytest.mark.parametrize('status,code,keeps_run',[(403,'run_placement_not_enabled',True),(409,'run_execution_changed',True),
    (503,'run_placement_unavailable',True),(403,'run_read_denied',False),(401,'identity_token_invalid',False)])
def test_run_placement_failure_clears_location_at_the_correct_authority(status,code,keeps_run):
    state={}
    async def scenario(origin):
        app=app_for(origin)
        async with app.run_test(size=(60,24)) as pilot:
            await open_detail(app,pilot);metadata=app.results['tasks']
            await click(app,pilot,'#task-files')
            await command(app,pilot,app.t('command_placement'))
            state.update(status=status,code=code)
            await pilot.press('f5');await settled(app,pilot)
            assert app.task_placement is None and 'Rack A' not in details(app)
            if keeps_run:
                assert app.results['tasks'] is metadata and app.task_file_page is None and app.selected_run=='run-example-1'
                await click(app,pilot,'#task-detail');assert 'simulation.py' in details(app)
                await click(app,pilot,'#task-files');assert app.task_file_page is not None
            else:
                assert app.selected_run is None and 'tasks' not in app.results and app.task_file_page is None
                if status==401:assert app.results=={} and app.paused
    with http_endpoint(responder(state)) as (origin,_):asyncio.run(scenario(origin))


@pytest.mark.parametrize('transition',['mode','scope','tab'])
@pytest.mark.parametrize('late_error',[False,True])
def test_delayed_run_placement_cannot_restore_location_or_revoke_replacement_context(transition,late_error):
    state={'started':threading.Event(),'release':threading.Event()}
    if late_error:state.update(status=403,code='run_read_denied')
    async def scenario(origin):
        app=app_for(origin)
        async with app.run_test(size=(60,24)) as pilot:
            await open_detail(app,pilot)
            app.query_one('#task-placement',Button).focus();await pilot.press('enter')
            for _ in range(100):
                if state['started'].is_set():break
                await pilot.pause(.02)
            assert state['started'].is_set()
            try:
                if transition=='mode':app.query_one('#task-detail',Button).focus();await pilot.press('enter')
                elif transition=='scope':app._read_projects();await pilot.pause(.04)
                else:app.query_one('#views',TabbedContent).active='resources';await pilot.pause(.04)
            finally:state['release'].set()
            await settled(app,pilot)
            assert app.task_placement is None and 'Rack A' not in details(app) and 'tasks' not in app._failed_views
            if transition=='mode':assert app.selected_run=='run-example-1'
            elif transition=='scope':assert app.tasks_workspace_key is None and app.task_projects is not None
            else:assert app.view=='resources'
    with http_endpoint(responder(state)) as (origin,_):asyncio.run(scenario(origin))


def test_run_placement_expiry_discards_registration_without_changing_allocation_or_reading(monkeypatch):
    start=datetime.now(timezone.utc);now=[start.timestamp()]
    monkeypatch.setattr('sai_cli.tui.time',SimpleNamespace(time=lambda:now[0]))
    body=sample()
    fmt=lambda value:value.isoformat().replace('+00:00','Z')
    allocation=body['placement']['allocation'];allocation['freshness']['observed_at']=fmt(start-timedelta(seconds=1))
    inventory=body['placement']['inventory'];inventory.update(published_at=fmt(start-timedelta(seconds=2)),expires_at=fmt(start+timedelta(seconds=10)))
    registration=body['placement']['nodes'][0]['registration'];registration.update(verified_at=fmt(start-timedelta(seconds=3)),valid_until=fmt(start+timedelta(seconds=5)))
    state={'body':body}
    async def scenario(origin,calls):
        app=app_for(origin)
        async with app.run_test(size=(40,24)) as pilot:
            await open_detail(app,pilot);await click(app,pilot,'#task-placement')
            original=app.task_placement.placement.allocation;count=len(calls)
            now[0]=start.timestamp()+6
            await pilot.pause(5.1)
            assert app.task_placement is original and isinstance(app.task_placement,SiteJobAllocationResult)
            assert 'Rack A' not in details(app) and '0,2' in details(app).replace(' ','')
            assert len(calls)==count and app.selected_run=='run-example-1'
    with http_endpoint(responder(state)) as (origin,calls):asyncio.run(scenario(origin,calls))
