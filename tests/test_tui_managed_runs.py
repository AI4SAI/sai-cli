import asyncio
from copy import deepcopy
from io import StringIO
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, Input, Static, TabbedContent

from sai_cli.auth import TokenLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.managed_runs import ManagedRunList, ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts
from sai_cli.tui import Workbench, modified_time_text, task_file_panel
from sai_cli.transport import JsonTransport
from test_managed_runs_contract import sample
from test_site_transport import http_endpoint
from test_tui import settled


def test_output_panel_preserves_full_paths_and_formats_mtime_without_losing_json_precision():
    data = sample("artifacts")
    path = "outputs/long-name-without-word-breaks-" + "result" * 9 + " #1.txt\x85"
    data["items"][0].update(relative_path=path, display_name="Friendly name")
    page = ManagedRunArtifacts.from_payload(data, workspace_key=data["workspace_key"], site_id=data["site_id"],
        run_ref=data["run_ref"], cursor=None, limit=100, request_id="files")
    output = StringIO()
    Console(file=output, width=38, color_system=None).print(task_file_panel(page))
    rendered = output.getvalue()
    assert "…" not in rendered and "Friendly name" not in rendered
    assert path.replace("\x85", "\\x85").replace(" ", "") in "".join(rendered.split())
    assert "Modified UTC: 2030-01-01 00:05:00" in rendered
    assert page.as_dict()["items"][0]["modified_at_ns"] == 1893456300000000001
    assert modified_time_text(0) == "Modified UTC: 1970-01-01 00:00:00"
    assert modified_time_text(10**30) == f"Modified: {10**30} ns since Unix epoch (outside calendar range)"


def details(app):
    output = StringIO()
    Console(file=output, width=100, color_system=None).print(app.query_one("#details", Static).content)
    return output.getvalue()


async def click(app, pilot, identifier):
    button = app.query_one(identifier, Button)
    await pilot.pause(button.active_effect_duration)
    button.focus()
    await pilot.press("enter")
    await settled(app, pilot)


async def command(app, pilot, title):
    await pilot.press("ctrl+p")
    app.screen.query_one(Input).value = title
    await pilot.pause(.2)
    await pilot.press("enter")
    await settled(app, pilot)


def client_for(origin):
    def forbidden(*args, **kwargs):
        pytest.fail("managed reads must not request a site capability or use the site origin")
    return PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=3),
        token_provider=SimpleNamespace(get=lambda: TokenLease("identity-token", None, "environment")),
        capability_provider=SimpleNamespace(get=forbidden), site_transport=SimpleNamespace(request=forbidden))


def test_tasks_http_workflow_is_explicit_paginated_and_retains_one_file_page(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    failure = None
    def reply(call, _):
        assert call["method"] == "GET" and call["bearer"] == "Bearer identity-token" and call["capability"] is None
        path = urlsplit(call["path"]).path
        query = parse_qs(urlsplit(call["path"]).query)
        assert query["workspace_key"] == ["project:project-example"] and query["site_id"] == ["site-a"]
        assert not set(query) & {"scope_type", "slurm_account_name", "cluster_id", "username", "user"}
        if failure:
            status, code = failure
            return status, {"detail": {"code": code, "message": "Managed read denied", "native": "hidden"}}
        if path.endswith("/runs"):
            result = sample("list")
            result["items"][0]["title"] = "train\x85part.sh"
            assert query["limit"] == ["50"]
            if "cursor" not in query:
                result.update(next_cursor="run-example-1", has_more=True)
            else:
                assert query["cursor"] == ["run-example-1"]
                result["items"][0].update(run_ref="run-example-2", title="older.py")
            return 200, result
        if path.endswith("/logs"):
            result = sample("log")
            stream = query["stream"][0]
            cursor = query.get("cursor", [f"log-{stream}-0"])[0]
            offset = int(cursor.rsplit("-", 1)[1])
            content = ("first page\n\x1b[red]literal\x07" if not offset else "second page\n") if stream == "stdout" else "stderr page\n"
            complete = offset > 0 or stream == "stderr"
            result.update(stream=stream, cursor=cursor, content=content, next_cursor=f"log-{stream}-{offset + len(content.encode())}",
                          complete=complete, truncated=not complete)
            assert query["max_bytes"] == ["65536"]
            return 200, result
        if path.endswith("/artifacts"):
            result = sample("artifacts")
            assert query["limit"] == ["100"]
            if "cursor" not in query:
                result.update(next_cursor="1", complete=False)
                result["items"][0].update(display_name="outputs/first result.txt\x85", relative_path="outputs/first result.txt\x85")
            else:
                assert query["cursor"] == ["1"]
                result.update(cursor="1")
                result["items"][0].update(display_name="outputs/second.txt", relative_path="outputs/second.txt")
            return 200, result
        assert path.endswith("/run-example-1")
        result = sample("detail")
        result["run"]["title"] = "train\x85part.sh"
        return 200, result

    async def scenario(client, calls):
        nonlocal failure
        app = Workbench(client, JobQuery(site_id="site-a", scope="org-account", account_name="org-unrelated"),
                        initial_view="tasks", storage_workspace_key="project:other", overview_account="other-account", refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            assert calls == [] and app.tasks_workspace_key is None
            app.query_one("#tasks-workspace", Input).value = "project:project-example"
            await click(app, pilot, "#load-tasks")
            assert isinstance(app.results["tasks"], ManagedRunList)
            assert app.results["tasks"].values["items"][0]["title"] == "train\x85part.sh"
            assert str(app.query_one("#tasks-table", DataTable).get_row("run-example-1")[1]) == "train\\x85part.sh"
            assert not app.query_one("#task-next", Button).disabled
            await click(app, pilot, "#task-next")
            assert app.results["tasks"].values["items"][0]["run_ref"] == "run-example-2"
            await click(app, pilot, "#task-start")
            app.query_one("#tasks-table", DataTable).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            metadata = app.results["tasks"]
            assert isinstance(metadata, ManagedRunDetail) and metadata.values["run"]["status"] == "completed"
            assert app.selected_run == "run-example-1" and "not live queue state" in details(app)
            assert metadata.as_dict()["run"]["title"] == "train\x85part.sh"
            assert "train\\x85part.sh" in details(app) and "\x85" not in details(app)
            assert str(app.query_one("#tasks-table", DataTable).get_row("run-example-1")[1]) == "train\\x85part.sh"
            for width in (40, 60, 100):
                await pilot.resize_terminal(width, 24)
                for name in ("task-detail", "task-stdout", "task-stderr", "task-files", "task-start", "task-next"):
                    button = app.query_one(f"#{name}", Button)
                    assert 0 <= button.region.x < button.region.right <= width
                app.save_screenshot(str(tmp_path / f"managed-task-{width}.svg"))
            await command(app, pilot, "Read task stdout")
            assert isinstance(app.task_file_page, ManagedRunLogs)
            assert "first page" in details(app) and "\\x1b[red]literal\\x07" in details(app)
            before = len(calls)
            app._tick(); await pilot.pause(.03)
            assert len(calls) == before
            await click(app, pilot, "#task-next")
            assert "second page" in details(app) and "first page" not in details(app)
            await click(app, pilot, "#task-start")
            assert "first page" in details(app) and "second page" not in details(app)
            await click(app, pilot, "#task-stderr")
            assert "stderr page" in details(app) and "first page" not in details(app)
            await click(app, pilot, "#task-files")
            assert isinstance(app.task_file_page, ManagedRunArtifacts) and "first result.txt\\x85" in details(app)
            app._tick(); await pilot.pause(.03)
            await click(app, pilot, "#task-next")
            assert "second.txt" in details(app) and "first result" not in details(app)
            failure = (403, "run_file_read_denied")
            await click(app, pilot, "#task-files")
            assert app.task_file_page is None and app.results["tasks"] is metadata
            assert "second.txt" not in details(app) and "completed" in details(app)
            assert "run_file_read_denied" in str(app.query_one("#status", Static).render())
            failure = (403, "run_scope_denied")
            app.results["storage"] = object()
            await click(app, pilot, "#task-detail")
            assert "tasks" not in app.results and "storage" in app.results and app.selected_run is None
            failure = None
            await click(app, pilot, "#load-tasks")
            app.query_one("#tasks-table", DataTable).focus(); await pilot.press("enter"); await settled(app, pilot)
            for name in ("resources", "jobs", "usage", "storage", "overview"):
                app.results[name] = object()
            failure = (401, "authentication_failed")
            await click(app, pilot, "#task-stdout")
            assert app.results == {} and app.task_file_page is None and app.paused
            assert app.job_query.account_name == "org-unrelated" and app.overview_account == "other-account"

    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(client_for(origin), calls))


@pytest.mark.parametrize("transition", ["workspace", "mode", "tab", "escape"])
def test_tasks_delayed_file_pages_cannot_replace_new_context(monkeypatch, transition):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    started, release = threading.Event(), threading.Event()
    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("/logs"):
            query = parse_qs(urlsplit(call["path"]).query)
            if query["stream"] == ["stdout"]:
                started.set(); assert release.wait(5)
                return 401, {"detail": "old read expired"}
            result = sample("log")
            result.update(stream="stderr", cursor="log-stderr-0", next_cursor="log-stderr-40")
            return 200, result
        if path.endswith("/runs"): return 200, sample("list")
        return 200, sample("detail")
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), tasks_workspace_key="project:project-example", initial_view="tasks", refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            try:
                await settled(app, pilot)
                await click(app, pilot, "#task-detail")
                await pilot.click("#task-stdout")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                if transition == "workspace":
                    app.query_one("#tasks-workspace", Input).value = "project:changed"
                    for _ in range(80):
                        if app.tasks_workspace_key is None: break
                        await pilot.pause(.02)
                    assert "tasks" not in app.results and app.task_file_page is None
                elif transition == "mode":
                    await pilot.click("#task-stderr")
                elif transition == "tab":
                    app.query_one("#views", TabbedContent).active = "storage"
                    await pilot.pause(.03)
                else:
                    await pilot.press("escape")
            finally:
                release.set()
            await settled(app, pilot)
            assert not app.paused
            if transition == "mode":
                assert app.task_file_page.values["stream"] == "stderr"
            else:
                assert app.task_file_page is None
            if transition == "tab":
                await command(app, pilot, "My managed tasks")
                assert app.view == "tasks" and isinstance(app.results["tasks"], ManagedRunDetail)
                assert app.task_file_page is None
            if transition == "workspace":
                assert "tasks" not in app.results and app.tasks_workspace_key is None
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(client_for(origin)))
    assert sum("/logs" in call["path"] for call in calls) == (2 if transition == "mode" else 1)
