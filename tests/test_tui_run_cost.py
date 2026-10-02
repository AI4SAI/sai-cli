import asyncio
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, DataTable, Static, TabbedContent

from sai_cli.client import JobQuery
from sai_cli.tui import Workbench
from test_managed_runs_contract import sample as run_sample
from test_managed_workspaces import sample as projects_sample
from test_run_cost import sample
from test_site_transport import http_endpoint
from test_tui import settled, catalog
from test_tui_managed_runs import click, client_for, details


def responder(state):
    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("/billing"):
            if state.get("started"):
                state["started"].set()
                assert state["release"].wait(10)
            if state.get("error"):
                return state.get("status", 403), {"detail": {"code": state["error"], "message": "Denied"}}
            return 200, sample(state.get("sample", "settled"))
        if path.endswith("/artifacts"): return 200, run_sample("artifacts")
        if path.endswith("/logs"): return 200, run_sample("log")
        if path.endswith("/workspaces"): return 200, projects_sample()
        if path.endswith("/runs"): return 200, run_sample("list")
        if path.endswith("resource-catalog"): return 200, catalog()
        return 200, run_sample("detail")
    return reply


def app_for(origin, language="en-US"):
    return Workbench(client_for(origin), JobQuery(site_id="site-a"), initial_view="tasks", language=language,
                     tasks_workspace_key="project:project-example", refresh_seconds=999)


async def open_detail(app, pilot):
    await settled(app, pilot)
    app.query_one("#tasks-table", DataTable).focus()
    await pilot.press("enter")
    await settled(app, pilot)


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_cost_is_explicit_manual_and_readable_at_all_terminal_sizes(tmp_path, monkeypatch, language):
    monkeypatch.delenv("NO_COLOR", raising=False)
    state = {}
    async def scenario(origin, calls):
        app = app_for(origin, language)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(40,18)) as pilot:
            await open_detail(app, pilot)
            metadata = app.results["tasks"]
            assert not any(call["path"].split("?")[0].endswith("/billing") for call in calls)
            assert app._presentation().automatic_refresh
            await click(app, pilot, "#task-cost")
            assert app.results["tasks"] is metadata and app.task_cost is not None
            assert not app._presentation().automatic_refresh and not app.check_action("pause", ())
            assert not app.query_one("#task-next").display
            assert any(command.title == app.t("command_cost") for command in app.get_system_commands(app.screen))
            before = len(calls); app._tick(); await pilot.press("f6"); await pilot.pause(.05)
            assert len(calls) == before
            for width, height in ((40,18), (60,24), (100,32)):
                await pilot.resize_terminal(width,height); await pilot.pause(.05)
                for name in ("detail", "stdout", "stderr", "files", "cost"):
                    region = app.query_one(f"#task-{name}").region
                    assert 0 <= region.x < region.right <= width and region.bottom < height
                pane = app.query_one("#details-scroll").region
                assert pane.height >= max(6, height // 2 - 1)
                visible = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
                assert "10.00" in visible and "3.00" in visible
                app.save_screenshot(str(tmp_path/f"cost-{language}-{width}x{height}.svg"))
            await pilot.press("w"); await pilot.pause(.05)
            assert parse_qs(urlsplit(opened[-1]).fragment.split("?",1)[1]) == {"run_ref": ["run-example-1"], "view": ["cost"]}
            state["sample"] = "gross-only"
            await pilot.press("f5"); await settled(app,pilot)
            assert "10.00" in details(app)
            assert "400 " + app.t("credit_unit") not in details(app)
            for name in ("pending", "unavailable", "not_chargeable"):
                state["sample"] = name
                await pilot.press("f5"); await settled(app,pilot)
                assert app.t("cost_"+name) in details(app)
                assert "0.00000000" not in details(app) and "10.00" not in details(app)
            await click(app,pilot,"#task-detail")
            assert app.task_cost is None and app._presentation().automatic_refresh
            await click(app,pilot,"#task-stdout")
            assert not app._presentation().automatic_refresh
    with http_endpoint(responder(state)) as (origin,calls): asyncio.run(scenario(origin,calls))


@pytest.mark.parametrize("code,status,retained", [
    ("run_cost_read_denied",403,True), ("identity_scope_denied",403,True),
    ("run_read_denied",403,False), ("identity_token_invalid",401,False),
])
def test_cost_denial_preserves_only_independently_authorized_facts(code,status,retained):
    state = {}
    async def scenario(origin):
        app = app_for(origin)
        async with app.run_test(size=(40,24)) as pilot:
            await open_detail(app,pilot)
            metadata = app.results["tasks"]
            await click(app,pilot,"#task-files")
            files = app.task_file_page
            await click(app,pilot,"#task-cost")
            state.update(error=code,status=status)
            await pilot.press("f5"); await settled(app,pilot)
            assert app.task_cost is None and "10.00" not in details(app)
            if retained:
                assert app.results["tasks"] is metadata and app.task_file_page is files
                assert app.selected_run == "run-example-1"
                await click(app,pilot,"#task-detail")
                assert "simulation.py" in details(app)
                await click(app,pilot,"#task-files")
                assert "energy result.txt" in details(app)
            else:
                assert "tasks" not in app.results and app.task_file_page is None
                assert app.selected_run is None
                if status == 401: assert app.results == {} and app.paused
    with http_endpoint(responder(state)) as (origin,_): asyncio.run(scenario(origin))


@pytest.mark.parametrize("transition", ["detail", "tab", "workspace"])
@pytest.mark.parametrize("late_error", [False, True])
def test_old_cost_response_cannot_restore_amounts_or_clear_new_context(transition,late_error):
    state = {"started": threading.Event(), "release": threading.Event()}
    if late_error: state.update(error="run_read_denied",status=403)
    async def scenario(origin):
        app = app_for(origin)
        async with app.run_test(size=(60,24)) as pilot:
            await open_detail(app,pilot)
            app.query_one("#task-cost",Button).focus(); await pilot.press("enter")
            for _ in range(100):
                if state["started"].is_set(): break
                await pilot.pause(.02)
            assert state["started"].is_set()
            try:
                if transition == "detail":
                    app.query_one("#task-detail",Button).focus(); await pilot.press("enter")
                elif transition == "tab":
                    app.query_one("#views",TabbedContent).active="resources"; await pilot.pause(.05)
                else:
                    app._read_projects(); await pilot.pause(.05)
            finally: state["release"].set()
            await settled(app,pilot)
            assert app.task_cost is None and "10.00" not in details(app)
            assert "tasks" not in app._failed_views
            if transition == "detail": assert app.selected_run == "run-example-1" and "tasks" in app.results
            if transition == "tab": assert app.view == "resources" and "resources" in app.results
            if transition == "workspace": assert app.tasks_workspace_key is None and app.task_projects is not None
    with http_endpoint(responder(state)) as (origin,_): asyncio.run(scenario(origin))
