from test_tui import show_view
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


@pytest.mark.parametrize("legacy", [False, True])
def test_queue_only_scope_with_no_record_choices_never_changes_account_or_reads_all_runs(monkeypatch, job_payload, legacy):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    query = JobQuery(site_id="site-a", scope="org-account", account_id="native-account-record") if legacy else JobQuery(site_id="site-a")
    def reply(call, _):
        if urlsplit(call["path"]).path.endswith("/workspaces"):
            return 200, {**workspace_sample(), "items": [], "has_more": False, "next_cursor": None}
        assert "/slurm/jobs" in call["path"]
        params = parse_qs(urlsplit(call["path"]).query)
        assert "workspace_key" not in params
        if legacy:
            assert params["slurm_account_id"] == ["native-account-record"]
        native = deepcopy(job_payload)
        if legacy:
            native.update(scope="org_account", slurm_account="server-owned-name", slurm_user="alice")
            native["items"][0]["slurm_account"] = "server-owned-name"
        return 200, native
    async def scenario(origin, calls):
        configured = client_for(origin)
        client = PortalClient(transport=configured.transport, token_provider=configured.token_provider)
        app = Workbench(client, query, initial_view="compute", refresh_seconds=999)
        async with app.run_test(size=(40, 18)) as pilot:
            await settled(app, pilot)
            assert app.compute_mode == "queue" and len(calls) == 1
            await click(app, pilot, "#compute-records")
            assert app.job_query == query and app.selection is None
            assert not any("/runs" in call["path"] for call in calls)
            assert app.query_one("#compute-scope", Select).value == ("legacy" if legacy else "self")
            assert app.t("projects_empty") in str(app.query_one("#compute-hint", Static).render())
            await click(app, pilot, "#compute-queue")
            assert app.job_query == query and len(calls) == 3
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(origin, calls))


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_one_compute_surface_preserves_scope_across_queue_records_and_resources(tmp_path, monkeypatch, job_payload, language, width):
    from textual.widgets import TabPane
    from test_tui import catalog
    from test_run_cost import sample as cost_sample
    from test_tui_artifact_continuation import response as file_reply, SECOND_REF
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    keys = ["personal:alice", "org:lab", "project:example", "project:second"]
    expired = False
    native_denied = False
    paged_choices = False

    def reply(call, count):
        path = urlsplit(call["path"]).path
        query = parse_qs(urlsplit(call["path"]).query)
        if path.endswith("/resource-catalog"):
            return 200, catalog()
        if path.endswith("/workspaces"):
            value = workspace_sample()
            page_keys = keys
            if paged_choices and "workspace_key" not in query:
                page_keys = keys[:2] if "cursor" not in query else keys[2:3]
                value.update(has_more="cursor" not in query,
                             next_cursor=page_keys[-1] if "cursor" not in query else None)
            value["items"] = [{"workspace_key": key, "label": "Same name", "organization_label": "Lab" if key.startswith("project:") else None}
                              for key in page_keys if not query.get("workspace_key") or query["workspace_key"] == [key]]
            return 200, value
        if expired:
            return 403, {"detail": {"code": "run_scope_denied", "message": "Denied"}}
        if "/slurm/" in path:
            if native_denied:
                return 403, {"detail": {"code": "site_read_not_authorized", "message": "Denied"}}
            value = deepcopy(job_payload)
            scope = query["scope_type"][0]
            key = query.get("workspace_key", [None])[0]
            assert not set(query) & {"slurm_account_id", "slurm_account_name", "user"}
            assert (key is None) == (scope == "self")
            value["scope"] = scope
            if key:
                assert scope == key.split(":")[0] + "_account"
                value.update(slurm_account="native-authorized", slurm_user="alice", visibility_role="member")
                value["items"][0]["slurm_account"] = "native-authorized"
            return 200, value
        key = query["workspace_key"][0]
        assert key in keys
        if path.endswith("/billing"):
            value = cost_sample()
        else:
            normalized = dict(call)
            normalized["path"] = call["path"].replace(key.replace(":", "%3A"), "project%3Aproject-example")
            _, value = file_reply(normalized, count)
        value["workspace_key"] = key
        return 200, value

    async def scenario(origin, calls):
        nonlocal expired, native_denied, paged_choices
        configured = client_for(origin)
        client = PortalClient(transport=configured.transport, token_provider=configured.token_provider)
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", language=language, refresh_seconds=999)
        async with app.run_test(size=(width, 24)) as pilot:
            await settled(app, pilot)
            assert [pane.id for pane in app.query(TabPane)] == ["overview", "resources", "compute", "storage"]
            assert len(app.query("#compute-table")) == 1 and not app.query("#jobs-table, #tasks-table")
            await click(app, pilot, "#compute-records")
            assert app.job_query.scope == "self" and app.job_query.workspace_key is None
            assert not any("/runs" in call["path"] for call in calls)
            assert app.query_one("#compute-scope", Select).value == "self"
            await pilot.pause()
            app.save_screenshot(str(tmp_path / f"compute-self-records-{language}-{width}.svg"))
            labels = app._project_labels()
            assert all(app.t("task_scope_" + key.split(":")[0]) in labels[key] for key in keys)
            assert "project:example" in labels["project:example"] and "project:second" in labels["project:second"]
            app.query_one("#compute-scope", Select).focus()
            await pilot.press("enter", "down", "enter"); await settled(app, pilot)
            assert app.job_query.workspace_key == keys[0]
            for key in keys:
                app.query_one("#compute-scope", Select).value = key
                await settled(app, pilot)
                await click(app, pilot, "#compute-queue")
                assert app.job_query.workspace_key == key and app.selected_run is None
                await click(app, pilot, "#compute-records")
                assert app.job_query.workspace_key == key and app.selected_job is None
            paged_choices = True
            await click(app, pilot, "#load-projects")
            await click(app, pilot, "#projects-next")
            assert app._choosing_scope and "project:second" not in app._project_labels()
            picker = app.query_one("#compute-scope", Select)
            picker.focus(); await pilot.press("enter", "enter")
            await pilot.pause()
            assert not picker.expanded and picker.value == "project:second"
            before = len(calls)
            await pilot.press("escape"); await settled(app, pilot)
            assert not app._choosing_scope and app.job_query.workspace_key == "project:second"
            assert app.query_one("#compute-table", DataTable).display
            assert len(calls) == before + 1 and "/runs?" in calls[-1]["path"]
            await click(app, pilot, "#load-projects")
            assert app._choosing_scope
            await click(app, pilot, "#compute-back")
            assert not app._choosing_scope and app.job_query.workspace_key == "project:second"
            paged_choices = False
            await pilot.pause()
            app.save_screenshot(str(tmp_path / f"compute-records-{language}-{width}.svg"))
            await click(app, pilot, "#compute-queue")
            await pilot.pause()
            app.save_screenshot(str(tmp_path / f"compute-queue-{language}-{width}.svg"))
            await click(app, pilot, "#compute-records")
            table = app.query_one("#compute-table", DataTable)
            table.focus(); await pilot.press("enter"); await settled(app, pilot)
            assert app.selected_run == "run-example-1"
            await click(app, pilot, "#compute-files")
            app.query_one("#task-artifacts").focus(); await pilot.press("home", "down", "enter"); await settled(app, pilot)
            assert app.selected_artifact[1] == SECOND_REF
            await click(app, pilot, "#compute-cost")
            assert app.task_cost is not None
            await click(app, pilot, "#compute-files")
            assert app.selected_artifact[1] == SECOND_REF
            app.query_one("#views", TabbedContent).active = "resources"; await settled(app, pilot)
            app.query_one("#views", TabbedContent).active = "compute"; await settled(app, pilot); await pilot.pause()
            assert app.selected_run == "run-example-1" and app.selected_artifact[1] == SECOND_REF
            assert app.job_query.workspace_key == "project:second"
            app.save_screenshot(str(tmp_path / f"compute-result-{language}-{width}.svg"))
            assert app.query_one("#details-scroll").region.height >= 5
            app.query_one("#views", TabbedContent).active = "resources"; await settled(app, pilot)
            app.query_one("#resources-table").focus(); await pilot.press("home", "enter")
            await click(app, pilot, "#use-partition")
            assert app.view == "compute" and app.compute_mode == "queue" and app.job_query.workspace_key == "project:second"
            assert app.job_query.partition == "gpu-standard" and app.selection is None
            app.query_one("#compute-table", DataTable).focus()
            await pilot.press("enter"); await settled(app, pilot)
            assert app.selected_job == "12345"
            app.query_one("#views", TabbedContent).active = "resources"; await settled(app, pilot)
            app.query_one("#resources-table").focus(); await pilot.press("home", "down", "enter")
            partition = app.selected_resource
            assert partition and partition != "gpu-standard"
            before = len(calls)
            await click(app, pilot, "#use-partition")
            assert app.selection is None and app.compute_mode == "queue"
            assert app.job_query.workspace_key == "project:second" and app.job_query.partition == partition
            assert len(calls) == before + 1
            assert urlsplit(calls[-1]["path"]).path == "/v1/slurm/jobs"
            assert parse_qs(urlsplit(calls[-1]["path"]).query)["partition"] == [partition]
            native_denied = True; await pilot.press("f5"); await settled(app, pilot)
            assert "jobs" not in app.results and app.job_query.workspace_key == "project:second"
            await click(app, pilot, "#compute-records")
            assert isinstance(app.results.get("tasks"), __import__("sai_cli.managed_runs", fromlist=["ManagedRunList"]).ManagedRunList)
            expired = True; await pilot.press("f5"); await settled(app, pilot)
            assert "tasks" not in app.results and app.job_query.workspace_key == "project:second" and app.selection is None
            assert app.query_one("#compute-scope", Select).value == "project:second"
            assert not app.query_one("#status").display
            assert "run_scope_denied" not in app.export_screenshot()
            app.save_screenshot(str(tmp_path / f"compute-expired-{language}-{width}.svg"))
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(origin, calls))


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
                        initial_view="compute", compute_mode="records", language=language, storage_workspace_key="personal:separate", refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            picker = app.query_one("#compute-scope", Select)
            assert picker.value == "legacy" and app.job_query.workspace_key is None and len(calls) == 1
            options = [label for label, value in picker._options if isinstance(value, str) and value not in {"self", "legacy"}]
            assert all(isinstance(label, Text) and not label.spans for label in options)
            assert "[red]材料模拟[/red]" in options[0].plain
            assert "project:choice-0" in options[0].plain and "project:choice-1" in options[1].plain
            picker.focus()
            await pilot.press("enter", "down")
            assert app.job_query.workspace_key is None and len(calls) == 1
            await pilot.press("escape")
            assert picker.value == "legacy" and app.job_query.workspace_key is None
            assert app.check_action("open_web", ()) is False
            await pilot.press("w")
            assert app.job_query.workspace_key is None and len(calls) == 1
            await click(app, pilot, "#projects-next")
            assert len(calls) == 2 and picker.value == "legacy" and app.job_query.workspace_key is None
            options = [label for label, value in picker._options if isinstance(value, str) and value not in {"self", "legacy"}]
            assert "project:project-example" not in options[0].plain
            picker.focus()
            await pilot.press("enter", "down")
            assert len(calls) == 2 and app.job_query.workspace_key is None
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.job_query.workspace_key == "project:project-example"
            assert "Materials" in str(app.query_one("#context", Static).render())
            assert app.job_query.workspace_key == "project:project-example" and app.job_query.account_name is None and app.storage_workspace_key == "personal:separate"
            await click(app, pilot, "#task-next")
            table = app.query_one("#compute-table", DataTable)
            table.focus()
            await pilot.press(*(["down"] * 25))
            await pilot.pause(.05)
            prior_scroll = table.scroll_y
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.selected_run == "run-older-25" and app.task_mode == "detail"
            assert Messages(language)("not_assigned") in details(app)
            await click(app, pilot, "#compute-stdout")
            assert "evidence line" in details(app)
            for width, height in ((40, 24), (60, 24), (100, 32), (40, 18)):
                await pilot.resize_terminal(width, height)
                await pilot.pause(.05)
                assert table.display == (width >= 100 and height >= 28)
                pane = app.query_one("#details-scroll")
                assert pane.region.height >= max(6, height // 2 - 1)
                descriptions = [key.description for key in app.query_one(Footer).query("FooterKey")]
                assert descriptions == [Messages(language)(key) for key in ("refresh", "back", "open_web", "palette")]
                for name in ("compute-detail", "compute-stdout", "compute-stderr", "compute-files", "compute-back", "compute-web"):
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
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", compute_mode="records", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.results["storage"] = object()
            failure = 400
            await click(app, pilot, "#projects-next")
            assert app.project_cursor == "project:project-example" and app._choosing_scope
            assert app.task_projects is None and app.job_query.workspace_key is None
            assert not app.query_one("#projects-first", Button).disabled
            before = len(calls)
            app._tick(); await pilot.pause(.03)
            assert len(calls) == before
            failure = None
            await click(app, pilot, "#projects-first")
            assert "cursor=" not in calls[-1]["path"] and app.query_one("#compute-scope", Select).value == "self"
            failure = 403
            await pilot.press("f5"); await settled(app, pilot)
            assert "storage" in app.results and app.task_projects is None
            assert app.query_one("#compute-scope", Select).value == "self" and app.job_query.workspace_key is None
            failure = 401
            await pilot.press("f5"); await settled(app, pilot)
            assert app.results == {} and app.paused and app.task_projects is None
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(client_for(origin), calls))


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_other_views_keep_one_language_and_source_facts(tmp_path, monkeypatch, language, job_payload):
    from test_tui import catalog, storage_sample, storage_workspaces_sample
    monkeypatch.delenv("NO_COLOR", raising=False)
    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("/storage/workspaces"):
            return 200, storage_workspaces_sample()
        if path.endswith("resource-catalog"):
            return 200, catalog()
        if path.endswith("quota-summary"):
            return 200, storage_sample("project:storage-example")
        if path.endswith("/overview"):
            return 200, overview_sample()
        return 200, job_payload
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="overview", language=language,
                        storage_workspace_key="project:storage-example", refresh_seconds=999)
        async with app.run_test(size=(100, 32)) as pilot:
            for view in ("overview", "resources", "jobs", "storage"):
                show_view(app, view)
                await settled(app, pilot)
                assert view in app.results
                if view == "overview":
                    target, expected = "overview-summary", "details" if language == "en-US" else "funds_detail"
                elif view == "storage":
                    target, expected = "storage-summary", "effective"
                elif view == "resources":
                    target, expected = "details", "resource_choose"
                else:
                    app.query_one("#compute-table", DataTable).focus()
                    await pilot.press("enter"); await settled(app, pilot)
                    target, expected = "details", "nodes_reason"
                output = StringIO()
                Console(file=output, color_system=None).print(app.query_one(f"#{target}", Static).content)
                assert Messages(language)(expected) in output.getvalue()
                if view == "overview":
                    assert "¥1,280.50" in output.getvalue() and "20,000" in output.getvalue()
                if view == "storage":
                    assert "-0.50000000" in output.getvalue() and app.t("portal_quota_observation") in output.getvalue()
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
