import asyncio
from copy import deepcopy
from io import StringIO
import threading
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, OptionList, Select, Static, TabbedContent

from sai_cli.client import JobQuery
from sai_cli.artifact_content import ManagedRunArtifactContent
from sai_cli.managed_runs import ManagedRunArtifacts, terminal_log
from sai_cli.tui import Workbench
from test_managed_runs_contract import sample
from test_site_transport import http_endpoint
from test_tui import settled
from test_tui_managed_runs import client_for, click
from test_managed_workspaces import sample as workspace_sample


LONG_PATH = "outputs/" + "长路径含Unicode-无空格" * 40 + "_[red]#1?%.txt\x85"
FIRST_REF = "artifact-" + "a" * 40
SECOND_REF = "artifact-" + "b" * 40
LATER_REF = "artifact-" + "c" * 40


def file_page(cursor=None):
    body = sample("artifacts")
    item = body["items"][0]
    if cursor is None:
        body.update(next_cursor="2", complete=False)
        body["items"] = [
            {**item, "artifact_ref": FIRST_REF, "relative_path": LONG_PATH},
            {**item, "artifact_ref": SECOND_REF, "relative_path": "outputs/第二个文件.txt"},
        ]
    else:
        assert cursor == "2"
        body.update(cursor="2", next_cursor=None, complete=True)
        body["items"] = [{**item, "artifact_ref": LATER_REF, "relative_path": "outputs/later.txt"}]
    return body


def response(call, _):
    assert call["method"] == "GET" and call["bearer"] == "Bearer identity-token" and call["capability"] is None
    url = urlsplit(call["path"])
    query = parse_qs(url.query)
    if url.path.endswith("/workspaces"):
        return 200, workspace_sample()
    assert query["workspace_key"] == ["project:project-example"] and query["site_id"] == ["site-a"]
    if url.path.endswith("/content"):
        artifact_ref = url.path.split("/")[-2]
        filename = LONG_PATH if artifact_ref == FIRST_REF else "outputs/第二个文件.txt" if artifact_ref == SECOND_REF else "outputs/later.txt"
        content = "first result\n\x1b[31m" if "cursor" not in query else "second result\n"
        offset = int(query["cursor"][0].split(":")[1]) if "cursor" in query else 0
        complete = offset > 0
        end = offset + len(content.encode())
        return 200, {"schema_version": "compute.run-artifact-content/v1", "workspace_key": "project:project-example", "site_id": "site-a",
            "run_ref": "run-example-1", "artifact_ref": artifact_ref, "relative_path": filename,
            "status": "available", "content": content, "offset": offset, "next_offset": end, "bytes_read": len(content.encode()),
            "complete": complete, "version": "d" * 64, "size_bytes": end if complete else end + len("second result\n"),
            "modified_at_ns": 1, "cursor": query.get("cursor", [None])[0], "next_cursor": None if complete else "d" * 64 + ":" + str(end),
            "observed_at": "2030-01-01T00:05:00Z", "freshness": {"source": "site-agent", "queried_at": "2030-01-01T00:05:00Z"}}
    if url.path.endswith("/artifacts"):
        assert query["limit"] == ["100"]
        return 200, file_page(query.get("cursor", [None])[0])
    if url.path.endswith("/runs"):
        return 200, sample("list")
    if url.path.endswith("/logs"):
        return 200, sample("log")
    assert url.path.endswith("/run-example-1")
    return 200, sample("detail")


async def open_files(app, pilot):
    await settled(app, pilot)
    app.query_one("#tasks-table", DataTable).focus()
    await pilot.press("enter")
    await settled(app, pilot)
    await click(app, pilot, "#task-files")
    await pilot.pause(.05)


def query(url):
    parsed = urlsplit(url)
    assert parsed.path == "/portal/" and parsed.query == ""
    route, encoded = parsed.fragment.split("?", 1)
    assert route == "/portal/workspaces/project%3Aproject-example/site-a/runs"
    return parse_qs(encoded)


@pytest.mark.parametrize("width", [40, 60, 100])
@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_files_keyboard_read_and_return_keep_the_exact_page_and_web_reference(tmp_path, monkeypatch, width, language):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    async def scenario(client, calls):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="tasks", refresh_seconds=999,
                        tasks_workspace_key="project:project-example", language=language)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(width, 24)) as pilot:
            await open_files(app, pilot)
            options = app.query_one("#task-artifacts", OptionList)
            assert options.has_focus and len(options.options) == 2 and app.selected_artifact is None
            assert isinstance(app.task_file_page, ManagedRunArtifacts)
            assert app.task_file_page.request_cursor is None
            rendered = StringIO()
            Console(file=rendered, width=max(10, width-6), color_system=None).print(options.options[0].prompt)
            assert terminal_log(LONG_PATH).replace(" ", "") in "".join(rendered.getvalue().split())
            assert "…" not in rendered.getvalue()
            before = len(calls)
            await pilot.press("home", "enter"); await settled(app, pilot)
            assert isinstance(app.task_file_page, ManagedRunArtifactContent) and app.task_mode == "content"
            assert app.selected_artifact[1] == FIRST_REF and not options.display
            app.save_screenshot(str(tmp_path / f"content-{language}-{width}.svg"))
            assert "first result" in "".join(ET.fromstring(app.export_screenshot()).itertext()).replace("\xa0", " ")
            assert len(calls) == before + 1
            await click(app, pilot, "#task-next")
            assert app.task_file_page.values["content"] == "second result\n"
            app.open_url = opened.append
            await pilot.press("w"); await settled(app, pilot)
            assert query(opened[-1])["artifact_ref"] == [FIRST_REF]
            before = len(calls)
            await pilot.press("escape"); await settled(app, pilot)
            assert app.task_mode == "files" and options.has_focus and len(calls) == before + 1
            await pilot.press("down", "enter"); await settled(app, pilot)
            assert app.selected_artifact[1] == SECOND_REF
            await pilot.press("escape"); await settled(app, pilot)
            await click(app, pilot, "#task-next")
            options.focus(); await pilot.press("home", "enter"); await settled(app, pilot)
            assert app.selected_artifact[0].request_cursor == "2"
            await click(app, pilot, "#open-task-web")
            assert query(opened[-1])["artifact_cursor"] == ["2"]
    with http_endpoint(response) as (origin, calls):
        asyncio.run(scenario(client_for(origin), calls))


@pytest.mark.parametrize("transition", ["page", "mode", "project", "tab", "escape", "permission"])
def test_confirmed_file_and_link_clear_before_context_changes(monkeypatch, transition):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    deny = False
    def reply(call, count):
        if deny:
            return 403, {"detail": {"code": "run_file_read_denied", "message": "Denied"}}
        return response(call, count)
    async def scenario(client):
        nonlocal deny
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="tasks", refresh_seconds=999,
                        tasks_workspace_key="project:project-example")
        app.open_url = lambda _: None
        async with app.run_test(size=(60,24)) as pilot:
            await open_files(app,pilot)
            options=app.query_one("#task-artifacts",OptionList)
            await pilot.press("home","enter","w")
            await settled(app,pilot)
            assert app.selected_artifact is not None and app._web_url is not None
            old_option=options.options[0]
            if transition=="page": app._task_page(start=False)
            elif transition=="mode": app._inspect_task("stdout")
            elif transition=="project": app._read_projects()
            elif transition=="tab":
                app.query_one("#views",TabbedContent).active="storage"
                await pilot.pause(.05)
            elif transition=="escape": app.action_back()
            else:
                deny=True
                app.action_refresh()
            if transition not in {"page", "permission"}: assert app.selected_artifact is None
            assert app._web_url is None
            await settled(app,pilot)
            if transition == "page":
                assert app.selected_artifact[1] == FIRST_REF and app.task_file_page.values["content"] == "second result\n"
                return
            assert app.selected_artifact is None
            if transition == "permission":
                assert app.task_mode == "files" and "tasks" in app.results
                deny = False; app.action_refresh(); await settled(app, pilot)
                assert isinstance(app.task_file_page, ManagedRunArtifacts) and "tasks" in app.results
            app.on_option_list_option_selected(OptionList.OptionSelected(options,old_option,0))
            assert app.selected_artifact is None
    with http_endpoint(reply) as (origin,_):asyncio.run(scenario(client_for(origin)))


def test_late_file_page_cannot_restore_old_selection_or_link(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    started,release=threading.Event(),threading.Event()
    block=False
    def reply(call,count):
        if block and "/content?" in call["path"]:
            started.set()
            assert release.wait(5)
        return response(call,count)
    async def scenario(client):
        nonlocal block
        app=Workbench(client,JobQuery(site_id="site-a"),initial_view="tasks",refresh_seconds=999,
                      tasks_workspace_key="project:project-example")
        app.open_url=lambda _:None
        async with app.run_test(size=(60,24)) as pilot:
            await open_files(app,pilot)
            await pilot.press("home","enter");await settled(app,pilot)
            await pilot.press("w");await settled(app,pilot)
            block=True;app.action_refresh()
            try:
                for _ in range(80):
                    if started.is_set():break
                    await pilot.pause(.02)
                assert started.is_set() and app.selected_artifact is not None and app._web_url is None
                app._inspect_task("detail")
            finally:release.set()
            await settled(app,pilot)
            assert app.task_mode=="detail" and app.task_file_page is None and app.selected_artifact is None
            assert not app.query_one("#task-artifacts",OptionList).display and app._web_url is None
    with http_endpoint(reply) as (origin,_):asyncio.run(scenario(client_for(origin)))


def test_content_wrong_path_cannot_replace_the_selected_file(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    def wrong_path(call, count):
        status, body = response(call, count)
        if "/content?" in call["path"]: body = {**body, "relative_path": "outputs/different.txt"}
        return status, body
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="tasks", refresh_seconds=999,
                        tasks_workspace_key="project:project-example")
        async with app.run_test(size=(60,24)) as pilot:
            await open_files(app,pilot)
            await pilot.press("home", "enter"); await settled(app,pilot)
            assert not isinstance(app.task_file_page, ManagedRunArtifactContent)
            assert "different.txt" not in str(app.query_one("#details",Static).content)
    with http_endpoint(wrong_path) as (origin,_): asyncio.run(scenario(client_for(origin)))
