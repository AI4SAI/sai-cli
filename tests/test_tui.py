from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from io import StringIO
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent
from rich.console import Console

from sai_cli.auth import TokenLease
from sai_cli.catalog import ResourceCatalog
from sai_cli.client import JobQuery, PortalClient
from sai_cli.errors import ForbiddenError
from sai_cli.storage_summary import StorageQuotaSummary
from sai_cli.tui import Workbench
from sai_cli.transport import JsonTransport
from test_site_transport import http_endpoint


async def settled(app, pilot):
    for _ in range(100):
        await pilot.pause(.02)
        if not app._reading and not app._pending:
            return
    raise AssertionError("reader did not finish")


def catalog():
    payload = json.loads((Path(__file__).resolve().parents[1] / "contracts/site-resource-catalog/v1/catalog.json").read_text())
    payload["site_id"] = "site-a"
    payload["compute"][0]["title"] = "[red]Literal GPU[/red]"
    return payload


def test_workbench_resource_comparison_to_job_and_estimate_over_http(tmp_path, job_payload, running_estimate_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    denied = 0

    def reply(call, count):
        nonlocal denied
        parsed = urlsplit(call["path"])
        if denied == 401:
            return 401, {"detail": "expired"}
        if parsed.path.endswith("resource-catalog"):
            return 200, catalog()
        if parsed.path.endswith("running-estimates"):
            return (denied, {"detail": "denied"}) if denied else (200, running_estimate_payload)
        if parsed.path.endswith("12345"):
            assert "partition" not in parse_qs(parsed.query)
        return 200, job_payload

    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(100, 32)) as pilot:
            await settled(app, pilot)
            table = app.query_one("#resources-table", DataTable)
            table.focus()
            await pilot.press("enter", "down", "enter")
            assert len(app.compared) == 2
            rendered = StringIO()
            Console(file=rendered, width=120).print(app.query_one("#details", Static).content)
            assert "[red]Literal GPU[/red]" in rendered.getvalue()
            # Use the first partition after toggling the second comparison off.
            await pilot.press("enter")
            await pilot.click("#use-partition")
            await settled(app, pilot)
            assert app.view == "jobs" and app.job_query.partition == "gpu-standard"
            app.query_one("#jobs-table", DataTable).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.selected_job == "12345"
            assert "Reason / nodes:" in str(app.query_one("#details", Static).render())
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.selected_job is None
            app.query_one("#views", TabbedContent).active = "usage"
            await settled(app, pilot)
            assert "jobs" in app.results and "usage" in app.results
            app.query_one("#usage-table", DataTable).focus()
            await pilot.press("down", "enter")
            assert app.selected_estimate == 1
            detail = str(app.query_one("#details", Static).render())
            assert "Not started" in detail and "Unknown" in detail
            app._tick()
            await pilot.pause(.05)
            assert str(app.query_one("#details", Static).render()) == detail
            nonlocal denied
            denied = 403
            await pilot.press("f5")
            await settled(app, pilot)
            assert "usage" not in app.results and "jobs" in app.results
            assert app.query_one("#usage-table", DataTable).row_count == 0
            assert str(app.query_one("#details", Static).render()) == ""
            denied = 401
            app.query_one("#views", TabbedContent).active = "jobs"
            await settled(app, pilot)
            assert not app.results and app.catalog is None and app.paused
            await pilot.resize_terminal(60, 24)
            app.save_screenshot(str(tmp_path / "workbench.svg"))

    with http_endpoint(reply) as (origin, calls):
        provider = SimpleNamespace(get=lambda: TokenLease("test-session", None, "environment"))
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2), token_provider=provider)
        asyncio.run(scenario(client))
    assert any("slurm/jobs/12345" in call["path"] for call in calls)
    assert all(call["method"] == "GET" for call in calls)


def test_scope_switch_discards_delayed_old_response_and_coalesces_refresh(job_payload):
    started, release = threading.Event(), threading.Event()
    calls = []
    concurrent = 0
    peak = 0

    class Client:
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")

        def list_jobs(self, query):
            nonlocal concurrent, peak
            concurrent += 1
            peak = max(peak, concurrent)
            calls.append(query.scope)
            try:
                if query.scope == "self":
                    started.set()
                    assert release.wait(5)
                    raise ForbiddenError("old scope denied")
                from sai_cli.contracts import JobResult
                payload = deepcopy(job_payload)
                payload.update(scope="org_account", slurm_user=None, slurm_account="org-example")
                payload["items"][0]["slurm_account"] = "org-example"
                return JobResult.from_payload(payload, request_id="new")
            finally:
                concurrent -= 1

    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(100, 30)) as pilot:
            try:
                await settled(app, pilot)
                app.query_one("#views", TabbedContent).active = "jobs"
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                app.query_one("#scope", Select).value = "org-account"
                app.query_one("#account", Input).value = "org-example"
                await pilot.click("#apply")
                assert app.query_one("#jobs-table", DataTable).row_count == 0
                for _ in range(20): app.request_read()
                release.set()
                await settled(app, pilot)
                assert calls == ["self", "org-account"] and peak == 1
                assert app.results["jobs"].scope == "org_account"
                assert "old scope denied" not in str(app.query_one("#status", Static).render())
                await pilot.press("f6")
                app._tick()
                await pilot.pause(.05)
                assert len(calls) == 2
            finally:
                release.set()
    asyncio.run(scenario())


def test_estimate_pages_use_snapshot_rows_with_nullable_or_duplicate_keys(running_estimate_payload):
    from sai_cli.contracts import RunningEstimateResult
    payload = deepcopy(running_estimate_payload)
    row = payload["items"][1]
    row["job_key"] = None
    payload["items"] = [deepcopy(row) for _ in range(105)]
    payload["count"] = 105
    result = RunningEstimateResult.from_payload(payload, request_id="usage")
    class Client:
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")
        def running_estimates(self, query): return result
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            app.query_one("#views", TabbedContent).active = "usage"
            await settled(app, pilot)
            table = app.query_one("#usage-table", DataTable)
            assert table.row_count == 100
            await pilot.click("#next")
            assert table.row_count == 5
            table.focus()
            await pilot.press("enter")
            assert app.selected_estimate == 100
            assert "Not started" in str(app.query_one("#details", Static).render())
    asyncio.run(scenario())


def storage_sample(workspace):
    return {
        "schema_version": "storage.quota-summary/v1", "workspace_key": workspace,
        "site_id": "site-a", "mount_id": "mount-example", "state": "drift",
        "source": "portal_quota_observation", "target_total_tib": "2.00000000",
        "effective_total_tib": "1.00000000", "used_tib": "1.50000000",
        "remaining_tib": "-0.50000000", "observed_soft_limit_tib": None,
        "observed_hard_limit_tib": "1.00000000", "used_inodes": 25,
        "inode_soft_limit": None, "inode_hard_limit": 100,
        "observed_at": "2026-09-23T00:00:00Z", "quota_updated_at": None,
    }


def test_storage_requires_its_own_workspace_and_denial_does_not_clear_jobs(job_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    denied = False

    def reply(call, count):
        parsed = urlsplit(call["path"])
        if parsed.path.endswith("resource-catalog"):
            return 200, catalog()
        if parsed.path.endswith("quota-summary"):
            assert parse_qs(parsed.query) == {"workspace_key": ["personal:storage-user"], "site_id": ["site-a"]}
            assert call["capability"] is None
            return (403, {"detail": "denied"}) if denied else (200, storage_sample("personal:storage-user"))
        return 200, job_payload

    async def scenario(client, calls):
        app = Workbench(client, JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            app.query_one("#views", TabbedContent).active = "jobs"
            await settled(app, pilot)
            app.query_one("#views", TabbedContent).active = "storage"
            await settled(app, pilot)
            await pilot.press("f5")
            app._tick()
            await settled(app, pilot)
            assert not any("quota-summary" in call["path"] for call in calls)
            assert not app.query_one("#job-scope-controls").display
            assert "Not selected" in str(app.query_one("#context", Static).render())
            app.query_one("#storage-workspace", Input).value = "personal:storage-user"
            await pilot.click("#load-storage")
            await settled(app, pilot)
            data = app.results["storage"].as_dict()
            assert data == storage_sample("personal:storage-user")
            output = StringIO()
            Console(file=output, color_system=None).print(app.query_one("#storage-summary", Static).content)
            content = output.getvalue()
            assert "-0.50000000" in content and "Needs review" in content
            assert "portal_quota_observation" in content and "2026-09-23T00:00:00Z" in content
            nonlocal denied
            denied = True
            await pilot.press("f5")
            await settled(app, pilot)
            assert "storage" not in app.results and "jobs" in app.results and app.catalog is not None
            assert str(app.query_one("#storage-summary", Static).render()) == ""
            app.query_one("#views", TabbedContent).active = "jobs"
            await settled(app, pilot)
            assert app.query_one("#job-scope-controls").display

    with http_endpoint(reply) as (origin, calls):
        provider = SimpleNamespace(get=lambda: TokenLease("test-session", None, "environment"))
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2), token_provider=provider)
        asyncio.run(scenario(client, calls))


def test_storage_workspace_edit_discards_old_read_and_does_not_infer_job_account():
    started, release = threading.Event(), threading.Event()
    calls = []

    class Client:
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")

        def storage_quota_summary(self, *, workspace_key, site_id):
            calls.append((workspace_key, site_id))
            if workspace_key == "personal:storage-user":
                started.set()
                assert release.wait(5)
            return StorageQuotaSummary.from_payload(
                storage_sample(workspace_key), workspace_key=workspace_key, site_id=site_id, request_id="storage",
            )

    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a", scope="org-account", account_name="org-compute"),
                        storage_workspace_key="personal:storage-user", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            try:
                await settled(app, pilot)
                assert calls == []
                app.query_one("#views", TabbedContent).active = "storage"
                for _ in range(80):
                    if started.is_set():
                        break
                    await pilot.pause(.02)
                assert started.is_set()
                app.query_one("#storage-workspace", Input).value = "project:storage-project"
                for _ in range(80):
                    if app.storage_workspace_key is None:
                        break
                    await pilot.pause(.02)
                assert app.storage_workspace_key is None and "storage" not in app.results
                assert str(app.query_one("#storage-summary", Static).render()) == ""
                app._tick()
                await pilot.click("#load-storage")
                release.set()
                await settled(app, pilot)
                assert calls == [("personal:storage-user", "site-a"), ("project:storage-project", "site-a")]
                assert app.results["storage"].values["workspace_key"] == "project:storage-project"
                assert "personal:storage-user" not in str(app.query_one("#storage-summary", Static).render())
                assert app.job_query.scope == "org-account" and app.job_query.account_name == "org-compute"
                app.query_one("#storage-workspace", Input).value = ""
                for _ in range(80):
                    if app.storage_workspace_key is None:
                        break
                    await pilot.pause(.02)
                assert "storage" not in app.results
                await pilot.press("f5")
                app._tick()
                await settled(app, pilot)
                assert len(calls) == 2
            finally:
                release.set()
    asyncio.run(scenario())


def test_storage_source_switch_discards_late_stored_sample():
    from sai_cli.native_quota import NativeQuotaResult
    from test_native_quota import native_payload

    started, release = threading.Event(), threading.Event()
    calls = []

    class Client:
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")

        def storage_quota_summary(self, *, workspace_key, site_id):
            calls.append("stored")
            started.set()
            assert release.wait(5)
            return StorageQuotaSummary.from_payload(storage_sample(workspace_key),
                workspace_key=workspace_key, site_id=site_id, request_id="stored")

        def storage_native_quota(self, *, workspace_key, site_id):
            calls.append("native")
            return NativeQuotaResult.from_payload(native_payload(),
                workspace_key=workspace_key, site_id=site_id, request_id="native")

    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), storage_workspace_key="project:example", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            try:
                await settled(app, pilot)
                app.query_one("#views", TabbedContent).active = "storage"
                for _ in range(80):
                    if started.is_set():
                        break
                    await pilot.pause(.02)
                assert started.is_set()
                app.query_one("#storage-source", Select).value = "native"
                await pilot.pause(.02)
                assert "storage" not in app.results
                release.set()
                await settled(app, pilot)
                assert calls == ["stored", "native"]
                assert isinstance(app.results["storage"], NativeQuotaResult)
                output = StringIO()
                Console(file=output, color_system=None).print(app.query_one("#storage-summary", Static).content)
                content = output.getvalue()
                assert "quota-example" in content and "Kind: project" in content
                assert "lustre_quota" in content and "portal_quota_observation" not in content
                assert "Native quota" in str(app.query_one("#status", Static).render())
            finally:
                release.set()
    asyncio.run(scenario())
