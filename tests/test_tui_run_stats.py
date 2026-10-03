import asyncio
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, DataTable, TabbedContent

from sai_cli.client import JobQuery
from sai_cli.tui import Workbench
from test_managed_runs_contract import sample as run_sample
from test_managed_workspaces import sample as project_sample
from test_run_cost import sample as cost_sample
from test_run_stats import sample
from test_site_transport import http_endpoint
from test_tui import settled, catalog
from test_tui_managed_runs import click, client_for, details


def responder(state):
    def reply(call,_):
        path=urlsplit(call["path"]).path
        if path.endswith("/stats"):
            if state.get("started"):
                state["started"].set();assert state["release"].wait(10)
            if state.get("status"):
                return state["status"],{"detail":{"code":"run_read_denied" if state["status"]==403 else "run_stats_unavailable","message":"Unavailable"}}
            return 200,sample(state.get("sample","available"))
        if path.endswith("/billing"):return 200,cost_sample()
        if path.endswith("/logs"):
            data=run_sample("log")
            stream=parse_qs(urlsplit(call["path"]).query)["stream"][0]
            data.update(stream=stream,cursor=data["cursor"].replace("stdout",stream),
                        next_cursor=data["next_cursor"].replace("stdout",stream))
            return 200,data
        if path.endswith("/artifacts"):return 200,run_sample("artifacts")
        if path.endswith("/workspaces"):return 200,project_sample()
        if path.endswith("/runs"):
            data=run_sample("list")
            data["items"].append({**data["items"][0],"run_ref":"run-other"})
            return 200,data
        if path.endswith("resource-catalog"):return 200,catalog()
        data=run_sample("detail")
        if path.endswith("run-other"):data["run"]["run_ref"]="run-other"
        return 200,data
    return reply


def app_for(origin,language="en-US"):
    return Workbench(client_for(origin),JobQuery(site_id="site-a"),initial_view="tasks",language=language,
                     tasks_workspace_key="project:project-example",refresh_seconds=999)


async def open_detail(app,pilot):
    await settled(app,pilot);app.query_one("#tasks-table",DataTable).focus()
    await pilot.press("enter");await settled(app,pilot)


@pytest.mark.parametrize("language",["zh-CN","en-US"])
def test_runtime_stats_are_explicit_manual_and_six_modes_fit_short_screens(tmp_path,monkeypatch,language):
    monkeypatch.delenv("NO_COLOR",raising=False)
    state={}
    async def scenario(origin,calls):
        app=app_for(origin,language);opened=[];app.open_url=opened.append
        async with app.run_test(size=(40,18)) as pilot:
            await open_detail(app,pilot)
            metadata=app.results["tasks"]
            assert not any('/stats?' in call["path"] for call in calls)
            await click(app,pilot,"#task-stats")
            assert app.results["tasks"] is metadata and app.task_stats is not None
            assert not app._presentation().automatic_refresh and not app.check_action("pause",())
            assert not app.query_one("#task-next").display
            assert any(command.title==app.t("command_stats") for command in app.get_system_commands(app.screen))
            before=len(calls);app._tick();await pilot.press("f6");await pilot.pause(.04)
            assert len(calls)==before
            for width,height in ((40,18),(60,24),(100,32)):
                await pilot.resize_terminal(width,height);await pilot.pause(.05)
                for mode in ("detail","stdout","stderr","files","cost","stats"):
                    region=app.query_one(f"#task-{mode}").region
                    assert 0<=region.x<region.right<=width and region.bottom<height, (mode,region)
                assert app.query_one("#task-evidence-actions").region.height==(2 if width<60 else 1)
                assert app.query_one("#details-scroll").region.height>=max(6,height//3)
                visible='\n'.join(strip.text for strip in app.screen._compositor.render_strips())
                assert '12345.batch' in visible and '240' in visible and '1073741824' in visible
                app.save_screenshot(str(tmp_path/f'stats-{language}-{width}x{height}.svg'))
            await pilot.press("w");await pilot.pause(.04)
            assert parse_qs(urlsplit(opened[-1]).fragment.split('?',1)[1])=={"run_ref":["run-example-1"],"view":["stats"]}
            for name in ("not_running","unavailable"):
                state["sample"]=name;await pilot.press("f5");await settled(app,pilot)
                assert app.t('stats_'+name) in details(app) and '240' not in details(app)
                assert '1073741824' not in details(app)
            for mode in ("cost","files","stdout","stderr","detail"):
                await click(app,pilot,f"#task-{mode}")
                assert app.task_stats is None
                assert app._presentation().automatic_refresh==(mode=="detail")
    with http_endpoint(responder(state)) as (origin,calls):asyncio.run(scenario(origin,calls))


@pytest.mark.parametrize("status",[503,403,401])
def test_stats_failure_clears_only_the_authority_that_failed(status):
    state={}
    async def scenario(origin):
        app=app_for(origin)
        async with app.run_test(size=(40,24)) as pilot:
            await open_detail(app,pilot);metadata=app.results["tasks"]
            await click(app,pilot,"#task-files")
            await click(app,pilot,"#task-stats")
            state['status']=status;await pilot.press('f5');await settled(app,pilot)
            assert app.task_stats is None and '1073741824' not in details(app)
            if status==503:
                assert app.results['tasks'] is metadata and app.task_file_page is None
                assert app.selected_run=='run-example-1'
                await click(app,pilot,'#task-detail');assert 'simulation.py' in details(app)
            else:
                assert 'tasks' not in app.results and app.task_file_page is None and app.selected_run is None
                if status==401:assert app.results=={} and app.paused
    with http_endpoint(responder(state)) as (origin,_):asyncio.run(scenario(origin))


@pytest.mark.parametrize("transition",["detail","tab","project","run"])
@pytest.mark.parametrize("late_error",[False,True])
def test_late_stats_do_not_restore_old_metrics_or_revoke_new_selection(transition,late_error):
    state={"started":threading.Event(),"release":threading.Event()}
    if late_error:state['status']=403
    async def scenario(origin):
        app=app_for(origin)
        async with app.run_test(size=(60,24)) as pilot:
            await open_detail(app,pilot)
            app.query_one('#task-stats',Button).focus();await pilot.press('enter')
            for _ in range(100):
                if state['started'].is_set():break
                await pilot.pause(.02)
            assert state['started'].is_set()
            try:
                if transition=='detail':
                    app.query_one('#task-detail',Button).focus();await pilot.press('enter')
                elif transition=='tab':
                    app.query_one('#views',TabbedContent).active='resources';await pilot.pause(.05)
                elif transition=='project':app._read_projects();await pilot.pause(.05)
                else:
                    await pilot.press('escape')
            finally:state['release'].set()
            await settled(app,pilot)
            assert app.task_stats is None and '1073741824' not in details(app) and 'tasks' not in app._failed_views
            if transition=='detail':assert app.selected_run=='run-example-1'
            if transition=='tab':assert app.view=='resources'
            if transition=='project':assert app.tasks_workspace_key is None and app.task_projects is not None
            if transition=='run':
                assert app.selected_run is None
                app.query_one('#tasks-table',DataTable).focus();await pilot.press('down','enter');await settled(app,pilot)
                assert app.selected_run=='run-other' and app.task_stats is None
    with http_endpoint(responder(state)) as (origin,_):asyncio.run(scenario(origin))
