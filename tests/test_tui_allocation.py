from test_tui import choose_compute_scope
import asyncio
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent

from sai_cli.auth import TokenProvider
from sai_cli.capability import CapabilityProvider
from sai_cli.catalog import ResourceCatalog
from sai_cli.client import JobQuery, PortalClient
from sai_cli.contracts import JobResult
from sai_cli.errors import AuthenticationError
from sai_cli.overview import AccountOverview
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.transport import JsonTransport
from sai_cli.tui import Workbench
from sai_cli.tui_views import allocation_panel
from test_capability import _settings
from test_overview import sample as overview_sample
from test_site_transport import http_endpoint, issuer
from test_tui import catalog, settled


def detail_text(app, width=60):
    output = StringIO()
    Console(file=output, width=width, color_system=None).print(app.query_one("#details", Static).content)
    return output.getvalue()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_allocation_panel_keeps_gres_units_indices_and_unknown_readable(site_allocation_payload, language, width):
    site_allocation_payload["allocation"]["nodes"][1]["gres"] = [
        {"name": "gpu", "type": "example", "count": 4, "indices": [0, 1, 2, 7]},
        {"name": "mps", "type": None, "count": 100, "indices": None},
        {"name": "shard", "type": None, "count": 0, "indices": None},
    ]
    result = SiteJobAllocationResult.from_payload(site_allocation_payload, request_id="panel")
    output = StringIO()
    Console(file=output, width=width, color_system=None).print(allocation_panel(result, language))
    text = output.getvalue()
    for expected in ("compute-a", "compute-b", "gpu:example", "mps", "shard", "0-2, 7",
                     "数量 100" if language == "zh-CN" else "Count 100",
                     "数量 0" if language == "zh-CN" else "Count 0",
                     "未知" if language == "zh-CN" else "Unknown"):
        assert expected in text
    assert ("Slurm 索引" if language == "zh-CN" else "Slurm indices") in text
    assert "CUDA/NVML" in text


def test_http_allocation_uses_exact_array_id_and_refreshes_one_complete_snapshot(tmp_path, job_payload, site_allocation_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    snapshot = deepcopy(site_allocation_payload)
    snapshot["job"]["name"] = "[red]literal[/red]"
    denied, block = False, False
    started, release = threading.Event(), threading.Event()

    def gateway_reply(call, count):
        assert call["bearer"] is None
        path = call["path"]
        if path.endswith("/allocation"):
            if denied:
                return 403, {"detail": "scope denied"}
            result = deepcopy(snapshot)
            result["job"]["array_task_id"] = path.split("/")[-2].split("_")[1]
            if block:
                started.set()
                assert release.wait(5)
            return 200, result
        tasks = ["0", "7"] if path.endswith("/jobs") else [path.rsplit("_", 1)[1]]
        return 200, {
            "schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a",
            "scope_type": "self", "subject": {"slurm_user": "alice", "slurm_account": None},
            "freshness": {**site_allocation_payload["freshness"], "source": "squeue" if len(tasks) == 2 else "scontrol"},
            "etag": "b" * 64, "has_more": False,
            "items": [{**job_payload["items"][0], "array_task_id": task} for task in tasks],
        }

    def central_reply(call, count):
        return (200, catalog()) if call["method"] == "GET" else issuer(call, count)

    async def scenario(client):
        nonlocal block, denied
        app = Workbench(client, JobQuery(site_id="site-a", cluster_id="cluster-a", partition="gpu-standard"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app._select_compute_mode("queue")
            await settled(app, pilot)
            await pilot.click("#compute-resources")
            await settled(app, pilot)
            assert app.selected_job == "12345_0" and isinstance(app.results["jobs"], SiteJobAllocationResult)
            assert "[red]literal[/red]" in detail_text(app)
            assert "compute-a" in detail_text(app) and "Unknown" in detail_text(app)
            app._tick()
            assert not app._pending and not app._reading
            await pilot.click("#compute-detail")
            await settled(app, pilot)
            assert app.job_mode == "detail" and app.results["jobs"].items[0].canonical_id == "12345_0"
            await pilot.press("escape")
            await settled(app, pilot)
            app.query_one("#compute-table", DataTable).focus()
            await pilot.press("down")
            await pilot.click("#compute-resources")
            await settled(app, pilot)
            assert app.selected_job == "12345_7"
            snapshot["restart_count"] = 1
            snapshot["freshness"]["observed_at"] = "2026-09-23T01:00:00Z"
            snapshot["allocation"] = {"status": "not_allocated", "nodes": []}
            block = True
            try:
                await pilot.press("f5")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set() and "jobs" not in app.results
                assert str(app.query_one("#details", Static).render()) == ""
            finally:
                release.set()
            await settled(app, pilot)
            assert "No nodes allocated" in detail_text(app) and "compute-a" not in detail_text(app)
            assert "Restart count: 1" in detail_text(app) and "01:00:00Z" in detail_text(app)
            snapshot["allocation"] = {"status": "unavailable", "nodes": None}
            block = False
            await pilot.press("f5")
            await settled(app, pilot)
            assert "Allocation unavailable" in detail_text(app) and "compute-a" not in detail_text(app)
            denied = True
            await pilot.press("f5")
            await settled(app, pilot)
            assert "jobs" not in app.results and "resources" in app.results
            assert str(app.query_one("#details", Static).render()) == ""

    with http_endpoint(central_reply) as (portal, issued), http_endpoint(gateway_reply) as (gateway, reads):
        settings = replace(_settings(tmp_path), base_url=portal, site_read_base_url=gateway)
        transport = JsonTransport(base_url=portal, timeout_seconds=2)
        client = PortalClient(transport=transport,
            token_provider=TokenProvider(settings=settings, transport=transport, environ={"SAI_TOKEN": "identity-session-token"}),
            capability_provider=CapabilityProvider(settings=settings, portal_transport=transport),
            site_transport=JsonTransport(base_url=gateway, timeout_seconds=2))
        asyncio.run(scenario(client))
    grants = [call["body"] for call in issued if call["method"] == "POST" and call["body"]["operation"] == "jobs.allocation"]
    assert {grant["job_id"] for grant in grants} == {"12345_0", "12345_7"}
    assert all(grant["partition"] is None and grant["scope_type"] == "self" for grant in grants)
    assert [call["path"] for call in reads if "/jobs/" in call["path"] and not call["path"].endswith("/allocation")] == ["/v1/site-read/jobs/12345_0"]


@pytest.mark.parametrize("language,truncated", [("zh-CN", True), ("en-US", False)])
def test_exact_job_lookup_keeps_scope_without_list_filters(tmp_path, job_payload, site_allocation_payload, monkeypatch, language, truncated):
    from test_managed_workspaces import sample as workspace_sample
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    visible = {**job_payload["items"][0], "slurm_account": "org-example", "state": "PD"}
    hidden = {**visible, "job_id": "67890", "array_task_id": "0", "state": "R", "partition": "other"}
    failure, block = 0, False
    started, release = threading.Event(), threading.Event()

    def central_reply(call, count):
        if call["method"] == "POST":
            return issuer(call, count)
        value = workspace_sample()
        value["items"] = [{"workspace_key": "org:example", "label": "Research", "organization_label": None}]
        return 200, value

    def gateway_reply(call, _):
        detail = call["path"].endswith("/jobs/67890_0")
        if detail and block:
            started.set()
            assert release.wait(5)
        if detail and failure:
            return failure, {"detail": {"code": "site_read_job_not_found" if failure == 404 else "site_read_not_authorized"}}
        return 200, {
            "schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a",
            "scope_type": "org_account", "subject": {"slurm_user": None, "slurm_account": "org-example"},
            "freshness": {**site_allocation_payload["freshness"], "source": "scontrol" if detail else "squeue"},
            "etag": "b" * 64, "has_more": truncated and not detail,
            "items": [hidden if detail else visible],
        }

    async def scenario(client):
        nonlocal block, failure
        query = JobQuery(site_id="site-a", cluster_id="cluster-a", scope="org-account", workspace_key="org:example",
                         partition="gpu-standard", states=("PD",), limit=1)
        app = Workbench(client, query, initial_view="compute", refresh_seconds=999, language=language)
        async with app.run_test(size=(100, 24)) as pilot:
            await settled(app, pilot)
            lookup, field = app.query_one("#job-lookup-controls"), app.query_one("#job-id", Input)
            table = app.query_one("#compute-table", DataTable)
            assert lookup.display and table.row_count == 1
            assert (app.t("queue_more") in str(app.query_one("#compute-hint", Static).render())) == truncated
            for width in (100, 60, 40):
                await pilot.resize_terminal(width, 24); await pilot.pause(.1)
                assert lookup.display and lookup.region.right <= width and field.region.width >= 8
                app.save_screenshot(str(tmp_path / f"lookup-{language}-{width}.svg"))
            field.value = "bad id"; field.focus()
            await pilot.press("enter")
            assert app.selected_job is None and app.t("job_id_invalid") in str(app.query_one("#status", Static).render())
            await pilot.press("escape")
            assert field.value == "" and app.focused is table
            await pilot.resize_terminal(100, 32)
            block = True
            field.value = "67890_0"; field.focus()
            try:
                await pilot.press("enter")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set() and app.selected_job == "67890_0"
                assert "jobs" not in app.results and table.row_count == 0
                assert not app._can_inspect_job() and "open_web" not in app._presentation().actions
            finally:
                release.set()
            await settled(app, pilot)
            assert app.results["jobs"].items[0].canonical_id == "67890_0" and not lookup.display
            assert app.job_query == query and "open_web" in app._presentation().actions
            await pilot.press("escape"); await settled(app, pilot)
            assert app.selected_job is None and lookup.display and field.value == "" and table.row_count == 1
            started.clear(); release.clear()
            field.value = "67890_0"; field.focus()
            try:
                await pilot.press("enter")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                await pilot.press("escape")
                assert app.selected_job is None
            finally:
                release.set()
            await settled(app, pilot)
            assert app.results["jobs"].items[0].canonical_id == "12345" and app._web_url is None
            block = False
            for failure in (404, 403, 401):
                field.value = "67890_0"; field.focus()
                await pilot.press("enter"); await settled(app, pilot)
                assert "jobs" not in app.results and app.selected_job is None and app._web_url is None
                assert app.job_query == query and lookup.display
                assert field.value == ("" if failure == 401 else "67890_0")
                if failure == 404:
                    assert app.t("job_not_found") in str(app.query_one("#compute-notice", Static).render())

    with http_endpoint(central_reply) as (portal, issued), http_endpoint(gateway_reply) as (gateway, reads):
        settings = replace(_settings(tmp_path), base_url=portal, site_read_base_url=gateway)
        transport = JsonTransport(base_url=portal, timeout_seconds=2)
        client = PortalClient(transport=transport,
            token_provider=TokenProvider(settings=settings, transport=transport, environ={"SAI_TOKEN": "identity-session-token"}),
            capability_provider=CapabilityProvider(settings=settings, portal_transport=transport),
            site_transport=JsonTransport(base_url=gateway, timeout_seconds=2))
        asyncio.run(scenario(client))
    grants = [call["body"] for call in issued if call["method"] == "POST"]
    assert all(grant["scope_type"] == "org_account" and grant["workspace_key"] == "org:example" for grant in grants)
    details = [grant for grant in grants if grant["operation"] == "jobs.detail"]
    assert details and all(grant["job_id"] == "67890_0" and grant["partition"] is None and grant["states"] == [] for grant in details)
    assert all(grant["partition"] == "gpu-standard" and grant["states"] == ["PD"] for grant in grants if grant["operation"] == "jobs.list")
    assert {call["path"] for call in reads if "/jobs/" in call["path"]} == {"/v1/site-read/jobs/67890_0"}


def test_allocation_missing_native_configuration_shows_existing_error_without_extra_request(tmp_path, job_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")

    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a", cluster_id="cluster-a"),
                        initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await pilot.click("#compute-resources")
            await settled(app, pilot)
            status = str(app.query_one("#status", Static).render())
            assert "check site connection settings" in status and "configuration_invalid" not in app.export_screenshot()
            assert not app.query_one("#status").display
            assert "jobs" not in app.results and str(app.query_one("#details", Static).render()) == ""

    with http_endpoint(lambda *_: (200, job_payload)) as (portal, reads):
        settings = replace(_settings(tmp_path), base_url=portal)
        transport = JsonTransport(base_url=portal, timeout_seconds=2)
        client = PortalClient(transport=transport, token_provider=TokenProvider(
            settings=settings, transport=transport, environ={"SAI_TOKEN": "identity-session-token"}))
        asyncio.run(scenario(client))
    assert len(reads) == 1 and reads[0]["path"].startswith("/v1/slurm/jobs?")


@pytest.mark.parametrize("transition", ["object", "detail", "scope", "escape", "tab"])
def test_late_allocation_never_overwrites_new_object_mode_or_scope(job_payload, site_allocation_payload, transition):
    started, release = threading.Event(), threading.Event()
    calls = []
    class Client:
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")
        def list_jobs(self, query):
            payload = deepcopy(job_payload)
            payload.update(scope=query.scope.replace("-", "_"), slurm_user="alice" if query.scope == "self" else None,
                           slurm_account=("org-example" if query.workspace_key else query.account_name))
            payload["items"] = [{**payload["items"][0], "array_task_id": task,
                "slurm_account": "org-example" if query.workspace_key else query.account_name or "personal-alice"} for task in ("0", "7")]
            payload["count"] = 2
            return JobResult.from_payload(payload, request_id="list")
        def show_job(self, identifier, query):
            payload = deepcopy(job_payload)
            payload["items"][0]["array_task_id"] = identifier.split("_")[1]
            return JobResult.from_payload(payload, request_id="detail")
        def job_allocation(self, identifier, query):
            calls.append(identifier)
            if identifier.endswith("_0"):
                started.set()
                assert release.wait(5)
            payload = deepcopy(site_allocation_payload)
            payload["job"]["array_task_id"] = identifier.split("_")[1]
            return SiteJobAllocationResult.from_payload(payload, request_id="allocation")
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await settled(app, pilot)
                await pilot.click("#compute-resources")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                if transition == "object":
                    app.query_one("#compute-table", DataTable).focus()
                    await pilot.press("down")
                    button = app.query_one("#compute-resources", Button)
                    # Textual suppresses another activation during its press animation.
                    await pilot.pause(button.active_effect_duration)
                    button.focus()
                    await pilot.press("enter")
                    assert app.selected_job == "12345_7" and app._pending
                elif transition == "detail":
                    await pilot.click("#compute-detail")
                elif transition == "scope":
                    await pilot.press("escape")
                    choose_compute_scope(app, "org:example")
                    await pilot.pause(.02)
                elif transition == "escape":
                    await pilot.press("escape")
                else:
                    app.query_one("#views", TabbedContent).active = "resources"
                    await pilot.pause(.02)
            finally:
                release.set()
            await settled(app, pilot)
            if transition == "object":
                assert calls == ["12345_0", "12345_7"] and app.results["jobs"].job.canonical_id == "12345_7"
            else:
                assert calls == ["12345_0"] and app.job_mode == ("allocation" if transition == "tab" else "detail")
                assert not any(isinstance(result, SiteJobAllocationResult) for result in app.results.values())
            if transition == "scope":
                assert app.results["jobs"].scope == "org_account"
    asyncio.run(scenario())


def test_allocation_auth_failure_clears_all_five_views_and_keeps_overview_account(job_payload):
    overview_calls = []
    class Client:
        transport = SimpleNamespace(base_url="https://portal.example")
        def account_overview(self, site, *, account):
            overview_calls.append(account)
            return AccountOverview.from_payload(overview_sample(), site_id=site, request_id="overview")
        def list_jobs(self, query):
            return JobResult.from_payload(job_payload, request_id="jobs")
        def job_allocation(self, identifier, query):
            raise AuthenticationError("session expired")
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), overview_account="org-example",
                        initial_view="overview", refresh_seconds=999)
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            for view in ("resources", "storage"):
                app.results[view] = object()
            app._select_compute_mode("queue")
            await settled(app, pilot)
            await pilot.click("#compute-resources")
            await settled(app, pilot)
            assert app.results == {} and app.paused and app.selected_job is None
            assert app.overview_account == "org-example" and overview_calls == ["org-example"]
            for name in ("details", "overview-summary", "storage-summary"):
                assert str(app.query_one(f"#{name}", Static).render()) == ""
    asyncio.run(scenario())
