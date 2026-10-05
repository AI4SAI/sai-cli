from test_tui import task_query
import asyncio
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, Select, Static, TabbedContent

from sai_cli.auth import TokenProvider
from sai_cli.capability import CapabilityProvider
from sai_cli.client import JobQuery, PortalClient
from sai_cli.transport import JsonTransport
from sai_cli.tui import Workbench
from test_capability import _settings
from test_managed_runs_contract import sample as run_sample
from test_managed_workspaces import sample as task_choices
from test_native_quota import native_payload
from test_site_transport import http_endpoint
from test_tui import catalog, settled, storage_sample, storage_workspaces_sample
from test_tui_managed_runs import click, client_for


STORAGE_CHOICES = "/v1/account/cli/storage/workspaces"
TASK_CHOICES = "/v1/compute/cli/workspaces"


def panel(app, name="storage-summary"):
    output = StringIO()
    Console(file=output, width=100, color_system=None).print(app.query_one("#" + name, Static).content)
    return output.getvalue()


def responder(state):
    def reply(call, _):
        path = urlsplit(call["path"]).path
        query = parse_qs(urlsplit(call["path"]).query)
        if path == "/v1/authz/storage-read":
            return 200, {"schema_version": "sai-storage-read-capability/v1", "capability": "fixture-storage-token",
                "expires_at": int(time.time()) + 120, "audience": "sai-site-read", "surface": "site-read",
                "operation": "storage.quota.read", **call["body"]}
        if path in {STORAGE_CHOICES, TASK_CHOICES}:
            key = query.get("workspace_key", [None])[0]
            if state.get("block_scope") == key and state.get("started"):
                state["started"].set(); assert state["release"].wait(10)
                if state.get("late_error"):
                    return 401, {"detail": {"code": "identity_token_invalid"}}
            if state.get("scope_status"):
                return state["scope_status"], {"detail": {"code": "scope_denied"}}
            if path == TASK_CHOICES:
                return 200, task_choices()
            if key:
                return 200, storage_workspaces_sample(key)
            if state.get("empty"):
                return 200, {**storage_workspaces_sample(), "items": []}
            if "cursor" not in query:
                value = storage_workspaces_sample("personal:first")
                value["items"].append({**value["items"][0], "workspace_key": "org:second"})
                value.update(has_more=True, next_cursor="org:second")
                return 200, value
            assert query["cursor"] == ["org:second"]
            return 200, storage_workspaces_sample("project:project-example")
        if path.endswith("quota-summary") or path.endswith("native-quota"):
            if state.get("quota_started") and path.endswith("quota-summary"):
                state["quota_started"].set(); assert state["quota_release"].wait(10)
            if state.get("quota_status"):
                return state["quota_status"], {"detail": {"code": "storage_read_denied"}}
            if path.endswith("native-quota"):
                value = native_payload(); value["workspace_key"] = "project:project-example"
                value["items"][0].update(used_bytes="0", used_inodes="0", block_soft_bytes="0", block_hard_bytes="0",
                                         inode_soft="0", inode_hard="0")
                return 200, value
            return 200, storage_sample(query["workspace_key"][0])
        if path.endswith("/runs"): return 200, run_sample("list")
        if path.endswith("resource-catalog"): return 200, catalog()
        return 200, run_sample("detail")
    return reply


async def choose_last(app, pilot, selector="storage-workspace"):
    picker = app.query_one("#" + selector, Select)
    picker.focus()
    await pilot.press("enter", "end")
    await pilot.pause(.1)
    await pilot.press("enter")
    await settled(app, pilot)


def native_client(origin, tmp_path):
    settings = replace(_settings(tmp_path), base_url=origin, site_read_base_url=origin)
    transport = JsonTransport(base_url=origin, timeout_seconds=3)
    return PortalClient(transport=transport,
        token_provider=TokenProvider(settings=settings, transport=transport, environ={"SAI_TOKEN": "synthetic-token"}),
        capability_provider=CapabilityProvider(settings=settings, portal_transport=transport), site_transport=transport)


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_storage_named_discovery_paging_keyboard_and_sources(tmp_path, monkeypatch, language):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def scenario(origin, calls):
        app = Workbench(native_client(origin, tmp_path), task_query(JobQuery(site_id="site-a", scope="org-account", account_name="org-compute"), "project:independent"),
                        initial_view="storage", language=language,  refresh_seconds=999)
        async with app.run_test(size=(40, 18)) as pilot:
            await settled(app, pilot)
            assert app.storage_workspace_key is None and app.query_one("#storage-workspace", Select).is_blank()
            assert len(calls) == 1 and not app._presentation().automatic_refresh
            picker = app.query_one("#storage-workspace", Select)
            assert all(value in str(label) for label, value in picker._options if isinstance(value, str))
            picker.focus(); await pilot.press("enter", "end")
            assert app.storage_workspace_key is None and len(calls) == 1
            await pilot.press("escape")
            await click(app, pilot, "#storage-next")
            assert app.storage_workspace_key is None and len(calls) == 2
            await choose_last(app, pilot)
            assert app.storage_workspace_key == "project:project-example" and "Materials" in app.storage_workspace_label
            assert "project:project-example" not in panel(app) and "Materials" in panel(app, "context")
            assert "portal_quota_observation" not in panel(app)
            assert app.job_query.account_name is None and app.job_query.workspace_key == "project:independent"
            for width, height in ((40, 18), (60, 24), (100, 32)):
                await pilot.resize_terminal(width, height); await pilot.pause(.1)
                for name in ("storage-workspace", "storage-source", "load-storage", "storage-first", "storage-next"):
                    region = app.query_one("#" + name).region
                    assert 0 <= region.x < region.right <= width and region.bottom < height, (name, region)
                visible = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
                assert "-0.50000000" in visible and app.t("effective") in visible
                app.save_screenshot(str(tmp_path / f"readable-storage-{language}-{width}x{height}.svg"))
            label = app.storage_workspace_label
            app.query_one("#storage-source", Select).value = "native"
            await settled(app, pilot)
            assert app.storage_workspace_label == label and app.storage_workspace_key == "project:project-example"
            assert app.t("quota_kind_project") in panel(app) and "lustre_quota" not in panel(app), (panel(app, "status"), calls)
            assert app.t("soft_limit") + ": " + app.t("unlimited") in panel(app)
            assert panel(app).count(app.t("unlimited")) == 4
            assert app.t("used") + ": " + app.t("bytes", count="0") in panel(app)
            assert app.results["storage"].values["items"][0]["block_soft_bytes"] == "0"
            app.save_screenshot(str(tmp_path / f"readable-native-{language}-100x32.svg"))
            assert len([call for call in calls if urlsplit(call["path"]).path == STORAGE_CHOICES]) == 2
            picker.focus(); await pilot.press("enter", "home", "enter"); await settled(app, pilot)
            assert app.storage_workspace_key is None and app.storage_workspace_label is None and "storage" not in app.results
            before = len(calls); app._tick(); await pilot.pause(.04); assert len(calls) == before
    with http_endpoint(responder({})) as (origin, calls): asyncio.run(scenario(origin, calls))


@pytest.mark.parametrize("view,key", [("tasks", "project:project-example"), ("storage", "org:preselected")])
def test_explicit_key_resolves_once_without_page_scanning_then_reads(view, key):
    async def scenario(origin, calls):
        app = Workbench(client_for(origin), task_query(JobQuery(site_id="site-a"), key if view == "tasks" else None), initial_view="compute" if view in {"jobs", "tasks"} else view, compute_mode="records" if view == "tasks" else "queue", refresh_seconds=999,
                        **({} if view == "tasks" else {"storage_workspace_key": key}))
        async with app.run_test(size=(40, 18)) as pilot:
            await settled(app, pilot)
            assert len(calls) == 2
            assert parse_qs(urlsplit(calls[0]["path"]).query) == {"site_id": ["site-a"], "limit": ["50"], "workspace_key": [key]}
            assert key not in panel(app, "context") and "Materials" in panel(app, "context")
            await pilot.press("f5"); await settled(app, pilot)
            assert len([call for call in calls if "/workspaces" in call["path"]]) == 1
    with http_endpoint(responder({})) as (origin, calls): asyncio.run(scenario(origin, calls))


@pytest.mark.parametrize("status", [401, 403, 503])
@pytest.mark.parametrize("phase", ["scope", "quota"])
def test_scope_and_quota_failures_clear_the_correct_named_context(status, phase):
    state = {}
    async def scenario(origin, calls):
        app = Workbench(client_for(origin), task_query(JobQuery(site_id="site-a"), "project:project-example"), initial_view="compute", compute_mode="records",
                         storage_workspace_key="org:preselected", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            compute_choices = app.task_projects
            assert compute_choices is not None
            if phase == "scope": state["scope_status"] = status
            app.query_one("#views", TabbedContent).active = "storage"; await settled(app, pilot)
            if phase == "quota":
                state["quota_status"] = status
                await pilot.press("f5"); await settled(app, pilot)
            assert "storage" not in app.results
            if status in {401, 403}:
                assert app.storage_workspace_key is None and app.storage_workspace_label is None
                assert app.storage_workspaces is None and app.query_one("#storage-workspace", Select).is_blank()
            elif phase == "quota": assert "Materials" in app.storage_workspace_label
            else:
                assert app.storage_workspace_label is None
                assert not any("quota-summary" in call["path"] for call in calls)
            if status == 401:
                assert app.results == {} and app.paused and app.job_query.workspace_key == "project:project-example" and app.scope_label is None
                assert app.task_projects is None and app.query_one("#compute-scope", Select).value == app.job_query.workspace_key
            else:
                assert app.scope_label is not None and "tasks" in app.results
                assert app.task_projects is compute_choices
    with http_endpoint(responder(state)) as (origin, calls): asyncio.run(scenario(origin, calls))


@pytest.mark.parametrize("late_error", [False, True])
@pytest.mark.parametrize("view", ["storage", "tasks"])
def test_late_exact_scope_name_or_denial_cannot_replace_another_tab(view, late_error):
    key = "project:project-example"
    state = {"block_scope": key, "started": threading.Event(), "release": threading.Event(), "late_error": late_error}
    async def scenario(origin):
        app = Workbench(client_for(origin), task_query(JobQuery(site_id="site-a"), key if view == "tasks" else None), initial_view="compute" if view in {"jobs", "tasks"} else view, compute_mode="records" if view == "tasks" else "queue", refresh_seconds=999,
                        **({} if view == "tasks" else {"storage_workspace_key": key}))
        async with app.run_test(size=(60, 24)) as pilot:
            try:
                for _ in range(100):
                    if state["started"].is_set(): break
                    await pilot.pause(.02)
                assert state["started"].is_set()
                app.query_one("#views", TabbedContent).active = "resources"; await pilot.pause(.05)
            finally: state["release"].set()
            await settled(app, pilot)
            assert app.view == "resources" and app.catalog is not None and not app.paused
            assert app.storage_workspace_label is None and app.scope_label is None
    with http_endpoint(responder(state)) as (origin, _): asyncio.run(scenario(origin))


def test_empty_storage_choices_have_one_empty_message_and_no_quota_request():
    async def scenario(origin, calls):
        app = Workbench(client_for(origin), JobQuery(site_id="site-a"), initial_view="storage", refresh_seconds=999)
        async with app.run_test(size=(40, 18)) as pilot:
            await settled(app, pilot)
            assert app.query_one("#storage-workspace", Select).disabled and app.storage_workspace_key is None
            assert panel(app) == app.t("storage_scopes_empty") + "\n"
            assert app.t("storage_choose") not in panel(app) and panel(app, "storage-hint").strip() == ""
            assert len(calls) == 1
    with http_endpoint(responder({"empty": True})) as (origin, calls): asyncio.run(scenario(origin, calls))
