import asyncio
from copy import deepcopy
from io import StringIO
from string import Formatter
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from rich.text import Text
from textual.widgets import Button, DataTable, Footer, Select, Static, TabbedContent

from sai_cli.client import JobQuery, PortalClient
from sai_cli.overview import AccountOverview
from sai_cli.overview_view import overview_rows
from sai_cli.tui import Workbench
from sai_cli.tui_messages import MESSAGES, Messages
from test_managed_runs_contract import sample
from test_managed_workspaces import sample as workspace_sample
from test_overview import sample as overview_sample
from test_site_transport import http_endpoint
from test_tui import settled
from test_tui_managed_runs import click, client_for, details


def test_language_catalog_placeholders_and_overview_financial_branches_agree():
    for key, pair in MESSAGES.items():
        assert len(pair) == 2 and all(pair)
        fields = [{field for _, field, _, _ in Formatter().parse(value) if field} for value in pair]
        assert fields[0] == fields[1], key
        for language in ("zh-CN", "en-US"):
            assert Messages(language)(key, **{field: "example" for field in fields[0]})
    for state in ("available", "not_authorized", "unavailable"):
        data = overview_sample()
        if state != "available":
            data["funds"] = {key: state if key == "state" else value if key == "currency" else None
                             for key, value in data["funds"].items()}
        result = AccountOverview.from_payload(data, site_id="site-a", request_id="language")
        before = deepcopy(result.values)
        zh = overview_rows(result, language="zh-CN")
        en = overview_rows(result, language="en-US")
        assert [row[2] for row in zh] == [row[2] for row in en]
        assert result.values == before
        if state == "available":
            for amount in ("¥1,280.50", "20,000"):
                assert amount in str(zh) and amount in str(en)
        else:
            assert "¥0" not in str(zh) + str(en)
            assert Messages("zh-CN")("funds_denied" if state == "not_authorized" else "funds_unavailable") in str(zh)
            assert Messages("en-US")("funds_denied" if state == "not_authorized" else "funds_unavailable") in str(en)


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_project_keyboard_discovery_and_narrow_task_return_over_http(tmp_path, language, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    first = workspace_sample()
    first["items"] = [
        {"workspace_key": f"project:choice-{index}", "label": "[red]材料模拟[/red]", "organization_label": "Research"}
        for index in range(2)
    ]
    first.update(has_more=True, next_cursor="project:choice-1")
    second = workspace_sample()
    second["items"][0]["label"] = "材料模拟 / Materials"
    list_reads = []

    def reply(call, _):
        parsed = urlsplit(call["path"])
        query = parse_qs(parsed.query)
        assert call["bearer"] == "Bearer identity-token" and call["capability"] is None
        if parsed.path.endswith("/workspaces"):
            assert query == {"site_id": ["site-a"], "limit": ["50"], **({"cursor": ["project:choice-1"]} if "cursor" in query else {})}
            return 200, second if "cursor" in query else first
        assert query["workspace_key"] == ["project:project-example"]
        assert query["site_id"] == ["site-a"]
        if parsed.path.endswith("/runs"):
            cursor = query.get("cursor", [None])[0]
            list_reads.append(cursor)
            data = sample("list")
            if cursor is None:
                data.update(has_more=True, next_cursor="run-example-1")
            else:
                assert cursor == "run-example-1"
                data["items"] = [{**data["items"][0], "run_ref": f"run-older-{index}", "title": f"结果 {index}.py"}
                                 for index in range(35)]
            return 200, data
        if parsed.path.endswith("/logs"):
            data = sample("log")
            data.update(content="输出结果\n" + "evidence line\n" * 16)
            data["next_cursor"] = "log-stdout-" + str(len(data["content"].encode()))
            data["run_ref"] = "run-older-25"
            return 200, data
        data = sample("detail")
        data["run"].update(run_ref="run-older-25", title="结果 25.py", scheduler_ref=None)
        return 200, data

    async def scenario(client, calls):
        app = Workbench(client, JobQuery(site_id="site-a", scope="org-account", account_name="org-independent"),
                        initial_view="tasks", language=language, storage_workspace_key="personal:separate", refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            picker = app.query_one("#tasks-project", Select)
            assert picker.is_blank() and app.tasks_workspace_key is None and len(calls) == 1
            options = [label for label, value in picker._options if isinstance(value, str)]
            assert all(isinstance(label, Text) and not label.spans for label in options)
            assert "[red]材料模拟[/red]" in options[0].plain
            assert "project:choice-0" in options[0].plain and "project:choice-1" in options[1].plain
            picker.focus()
            await pilot.press("enter", "down")
            assert app.tasks_workspace_key is None and len(calls) == 1
            await pilot.press("escape")
            assert picker.is_blank() and app.tasks_workspace_key is None
            assert app.check_action("open_web", ()) is False
            await pilot.press("w")
            assert app.tasks_workspace_key is None and len(calls) == 1
            await click(app, pilot, "#projects-next")
            assert len(calls) == 2 and picker.is_blank() and app.tasks_workspace_key is None
            options = [label for label, value in picker._options if isinstance(value, str)]
            assert "project:project-example" not in options[0].plain
            picker.focus()
            await pilot.press("enter", "down")
            assert len(calls) == 2 and app.tasks_workspace_key is None
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.tasks_workspace_key == "project:project-example"
            assert "Materials" in str(app.query_one("#context", Static).render())
            assert app.job_query.account_name == "org-independent" and app.storage_workspace_key == "personal:separate"
            await click(app, pilot, "#task-next")
            table = app.query_one("#tasks-table", DataTable)
            table.focus()
            await pilot.press(*(["down"] * 25))
            await pilot.pause(.05)
            prior_scroll = table.scroll_y
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.selected_run == "run-older-25" and app.task_mode == "detail"
            assert Messages(language)("not_assigned") in details(app)
            await click(app, pilot, "#task-stdout")
            assert "evidence line" in details(app)
            for width, height in ((40, 24), (60, 24), (100, 32), (40, 18)):
                await pilot.resize_terminal(width, height)
                await pilot.pause(.05)
                assert table.display == (width >= 100 and height >= 28)
                pane = app.query_one("#details-scroll")
                assert pane.region.height >= max(6, height // 2 - 1)
                descriptions = [key.description for key in app.query_one(Footer).query("FooterKey")]
                assert descriptions == [Messages(language)(key) for key in ("refresh", "back", "open_web", "palette")]
                for name in ("task-detail", "task-stdout", "task-stderr", "task-files", "task-back", "open-task-web"):
                    region = app.query_one(f"#{name}").region
                    assert 0 <= region.x < region.right <= width
                app.save_screenshot(str(tmp_path / f"workflow-{language}-{width}-{height}.svg"))
            await pilot.resize_terminal(40, 24)
            before = len(calls)
            app._tick()
            await pilot.pause(.03)
            assert len(calls) == before
            await pilot.press("escape")
            await settled(app, pilot)
            assert list_reads == [None, "run-example-1", "run-example-1"]
            assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == "run-older-25"
            assert table.scroll_y == prior_scroll and table.has_focus
            assert app.task_file_page is None and app.selected_run is None
            assert not app.query_one("#details-scroll").display
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(client_for(origin), calls))


def test_discovery_failure_keeps_cursor_until_explicit_first_and_revokes_only_tasks():
    failure = None
    def reply(call, _):
        if failure:
            return failure, {"detail": {"code": "workspace_cursor_invalid" if failure == 400 else "run_scope_denied", "message": "denied"}}
        data = workspace_sample()
        if "cursor=" not in call["path"]:
            data.update(has_more=True, next_cursor="project:project-example")
        else:
            data["items"][0]["workspace_key"] = "project:second"
        return 200, data
    async def scenario(client, calls):
        nonlocal failure
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="tasks", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.results["storage"] = object()
            failure = 400
            await click(app, pilot, "#projects-next")
            assert app.project_cursor == "project:project-example" and app.task_mode == "projects"
            assert app.task_projects is None and app.tasks_workspace_key is None
            assert not app.query_one("#projects-first", Button).disabled
            before = len(calls)
            app._tick(); await pilot.pause(.03)
            assert len(calls) == before
            failure = None
            await click(app, pilot, "#projects-first")
            assert "cursor=" not in calls[-1]["path"] and app.query_one("#tasks-project", Select).is_blank()
            failure = 403
            await pilot.press("f5"); await settled(app, pilot)
            assert "storage" in app.results and app.task_projects is None
            assert app.query_one("#tasks-project", Select).is_blank() and app.tasks_workspace_key is None
            failure = 401
            await pilot.press("f5"); await settled(app, pilot)
            assert app.results == {} and app.paused and app.task_projects is None
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(client_for(origin), calls))


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_other_views_keep_one_language_and_source_facts(tmp_path, monkeypatch, language, job_payload, running_estimate_payload):
    from test_tui import catalog, storage_sample
    monkeypatch.delenv("NO_COLOR", raising=False)
    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("resource-catalog"):
            return 200, catalog()
        if path.endswith("running-estimates"):
            return 200, running_estimate_payload
        if path.endswith("quota-summary"):
            return 200, storage_sample("project:storage-example")
        if path.endswith("/overview"):
            return 200, overview_sample()
        return 200, job_payload
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="overview", language=language,
                        storage_workspace_key="project:storage-example", refresh_seconds=999)
        async with app.run_test(size=(100, 32)) as pilot:
            for view in ("overview", "resources", "jobs", "usage", "storage"):
                app.query_one("#views", TabbedContent).active = view
                await settled(app, pilot)
                assert view in app.results
                if view == "overview":
                    target, expected = "overview-summary", "details" if language == "en-US" else "funds_detail"
                elif view == "storage":
                    target, expected = "storage-summary", "effective"
                elif view == "resources":
                    target, expected = "details", "resource_choose"
                elif view == "usage":
                    target, expected = "details", "usage_choose"
                else:
                    app.query_one("#jobs-table", DataTable).focus()
                    await pilot.press("enter"); await settled(app, pilot)
                    target, expected = "details", "nodes_reason"
                output = StringIO()
                Console(file=output, color_system=None).print(app.query_one(f"#{target}", Static).content)
                assert Messages(language)(expected) in output.getvalue()
                if view == "overview":
                    assert "¥1,280.50" in output.getvalue() and "20,000" in output.getvalue()
                if view == "storage":
                    assert "-0.50000000" in output.getvalue() and "portal_quota_observation" in output.getvalue()
                for width, height in ((100, 32), (60, 24), (40, 24)):
                    await pilot.resize_terminal(width, height)
                    await pilot.pause(.05)
                    if view == "overview" and language == "en-US" and width == 40:
                        visible = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
                        assert "¥1,280.50" in visible and "20,000" in visible
                        assert "Messages" in visible and "4 ·" in visible
                        assert "Login identity" in visible
                    app.save_screenshot(str(tmp_path / f"{view}-{language}-{width}-{height}.svg"))
            app.query_one("#storage-workspace").focus()
            await pilot.press("ctrl+q")
            assert app._exit
    with http_endpoint(reply) as (origin, calls):
        configured = client_for(origin)
        asyncio.run(scenario(PortalClient(transport=configured.transport, token_provider=configured.token_provider)))
