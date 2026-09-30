import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent
from textual.containers import Horizontal

from sai_cli.auth import TokenLease, TokenProvider
from sai_cli.capability import CapabilityProvider
from sai_cli.catalog import ResourceCatalog
from sai_cli.client import JobQuery, PortalClient
from sai_cli.contracts import JobResult
from sai_cli.errors import AuthenticationError
from sai_cli.job_web_context import JobWebContext
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.transport import JsonTransport
from sai_cli.tui import Workbench
from test_capability import _settings
from test_job_web_context import sample
from test_site_transport import http_endpoint, issuer
from test_tui import catalog, settled


async def open_web(app, pilot):
    button = app.query_one("#open-job-web", Button)
    await pilot.pause(button.active_effect_duration)
    assert button.display and not button.disabled
    button.focus()
    await pilot.press("enter")
    await settled(app, pilot)


def test_real_http_navigation_uses_portal_mapping_and_preserves_the_displayed_observation(
    tmp_path, job_payload, site_allocation_payload, monkeypatch,
):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    job_payload["items"][0].update(array_task_id="0", slurm_account="legacy-project")
    site_allocation_payload["job"] = deepcopy(job_payload["items"][0])
    site_allocation_payload["restart_count"] = 0
    mapping, failure = sample(), None
    def central(call, count):
        if call["method"] == "POST":
            return issuer(call, count)
        assert call["bearer"] == "Bearer identity-session-token" and call["capability"] is None
        assert urlsplit(call["path"]).path == "/v1/slurm/cli/jobs/12345_0/web-context"
        if failure:
            status, code = failure
            return status, {"detail": {"code": code, "message": "Web context is unavailable"}}
        return 200, mapping
    def gateway(call, _):
        assert call["bearer"] is None and call["capability"]
        if call["path"].endswith("/allocation"):
            return 200, site_allocation_payload
        return 200, {
            "schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a", "scope_type": "self",
            "subject": {"slurm_user": "alice", "slurm_account": None}, "items": job_payload["items"],
            "etag": "b" * 64, "has_more": False,
            "freshness": {**site_allocation_payload["freshness"],
                "source": "squeue" if call["path"].endswith("/jobs") else "scontrol"},
        }

    async def scenario(client):
        nonlocal failure
        app = Workbench(client, JobQuery(site_id="site-a", cluster_id="cluster-a", partition="gpu-standard"),
                        initial_view="jobs", overview_account="org-unrelated", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert not app.query_one("#open-job-web", Button).display
            app.query_one("#jobs-table", DataTable).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            await open_web(app, pilot)
            assert len(opened) == 1
            assert str(app.query_one("#web-link", Static).content.style) == f"link {opened[-1]}"
            context = json.loads(parse_qs(urlsplit(opened[-1]).fragment.split("?", 1)[1])["job_context"][0])
            assert context == {"workspace_key": "project:project-example", "site_id": "site-a", "cluster_id": "cluster-a",
                "job_id": "12345_0", "observed_at": site_allocation_payload["freshness"]["observed_at"],
                "submit_time": job_payload["items"][0]["submit_time"], "restart_count": None}
            assert urlsplit(opened[-1]).netloc == urlsplit(client.transport.base_url).netloc
            assert app.overview_account == "org-unrelated"
            await pilot.click("#view-allocation")
            await settled(app, pilot)
            assert not app.query_one("#web-link-row", Horizontal).display
            snapshot = app.results["jobs"]
            for changed in ("submit_time", "restart_count"):
                original = mapping[changed]
                mapping[changed] = "2026-07-31T01:00:00Z" if changed == "submit_time" else 1
                await open_web(app, pilot)
                assert len(opened) == 1 and app.results["jobs"] is snapshot
                assert "Refresh this view" in str(app.query_one("#status", Static).render())
                mapping[changed] = original
            mapping["submit_time"] = mapping["restart_count"] = None
            await open_web(app, pilot)
            assert len(opened) == 2 and app.results["jobs"] is snapshot
            context = json.loads(parse_qs(urlsplit(opened[-1]).fragment.split("?", 1)[1])["job_context"][0])
            assert context["restart_count"] == 0 and context["submit_time"] == snapshot.job.values["submit_time"]
            app._tick()
            await pilot.pause(.02)
            assert not app._pending and len(opened) == 2
            for failure in ((403, "job_navigation_workspace_denied"), (503, "source_unavailable")):
                await open_web(app, pilot)
                assert app.results["jobs"] is snapshot and len(opened) == 2
                assert not app.query_one("#web-link-row", Horizontal).display
                assert failure[1] in str(app.query_one("#status", Static).render())
            failure = (403, "site_read_not_authorized")
            await open_web(app, pilot)
            assert "jobs" not in app.results and not app.query_one("#open-job-web", Button).display
            failure = None
            await pilot.press("f5")
            await settled(app, pilot)
            for name in ("resources", "usage", "storage", "overview"):
                app.results[name] = object()
            failure = (401, "authentication_failed")
            await open_web(app, pilot)
            assert app.results == {} and app.paused and app.selected_job is None and len(opened) == 2

    with http_endpoint(central) as (portal, central_calls), http_endpoint(gateway) as (site, site_calls):
        settings = replace(_settings(tmp_path), base_url=portal, site_read_base_url=site)
        transport = JsonTransport(base_url=portal, timeout_seconds=2)
        client = PortalClient(transport=transport,
            token_provider=TokenProvider(settings=settings, transport=transport, environ={"SAI_TOKEN": "identity-session-token"}),
            capability_provider=CapabilityProvider(settings=settings, portal_transport=transport),
            site_transport=JsonTransport(base_url=site, timeout_seconds=2))
        asyncio.run(scenario(client))
    web_calls = [c for c in central_calls if c["method"] == "GET"]
    assert len(web_calls) == 8
    assert all(parse_qs(urlsplit(c["path"]).query) == {
        "site_id": ["site-a"], "cluster_id": ["cluster-a"], "scope_type": ["self"], "source_preference": ["live"],
    } for c in web_calls)
    assert all("web-context" not in c["path"] for c in site_calls)


def test_headless_browser_failure_keeps_a_clickable_copyable_link_until_scope_changes(job_payload, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    def reply(call, _):
        if urlsplit(call["path"]).path.endswith("/web-context"):
            return 200, sample()
        query = parse_qs(urlsplit(call["path"]).query)
        payload = deepcopy(job_payload)
        account = query.get("slurm_account_name", [None])[0]
        payload.update(scope=query["scope_type"][0], slurm_user=None if account else "alice", slurm_account=account)
        payload["items"][0].update(array_task_id="0", slurm_account=account or "personal-alice")
        return 200, payload
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999)
        def no_browser(url):
            raise OSError("no local desktop browser")
        app.open_url = no_browser
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await pilot.click("#view-job")
            await settled(app, pilot)
            snapshot = app.results["jobs"]
            await open_web(app, pilot)
            link = app.query_one("#web-link", Static)
            url = JobWebContext.from_payload(sample(), request_id="web").web_url(client.transport.base_url,
                observed_at=snapshot.freshness.queried_at, submit_time=snapshot.items[0].values["submit_time"], restart_count=None)
            assert app.query_one("#web-link-row", Horizontal).display
            assert str(link.content) == "Open job in browser" and str(link.content.style) == f"link {url}"
            assert app._web_url == url and app.clipboard == ""
            assert "Web link ready" in str(app.query_one("#status", Static).render())
            await pilot.click("#copy-web-link")
            assert app.clipboard == url
            assert app.results["jobs"] is snapshot and link.region.width <= app.size.width
            app.save_screenshot(str(tmp_path / "web-link.svg"))
            await pilot.press("escape")
            await settled(app, pilot)
            app.query_one("#scope", Select).value = "org-account"
            app.query_one("#account", Input).value = "org-example"
            await pilot.click("#apply")
            await settled(app, pilot)
            assert not app.query_one("#web-link-row", Horizontal).display and str(link.content) == ""
            assert app._web_url is None
            assert app.results["jobs"].scope == "org_account"
    with http_endpoint(reply) as (origin, calls):
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2),
                             token_provider=SimpleNamespace(get=lambda: TokenLease("identity-token", None, "environment")))
        asyncio.run(scenario(client))
    assert sum("/web-context" in call["path"] for call in calls) == 1


@pytest.mark.parametrize("transition", ["mode", "scope", "tab", "escape", "refresh"])
def test_navigation_is_one_serialized_action_and_late_responses_cannot_open_a_browser(
    job_payload, site_allocation_payload, transition,
):
    started, release = threading.Event(), threading.Event()
    calls = []
    class Client:
        transport = SimpleNamespace(base_url="https://portal.example.org")
        def resource_catalog(self, site):
            return ResourceCatalog.from_payload(catalog(), site_id=site, request_id="catalog")
        def list_jobs(self, query):
            payload = deepcopy(job_payload)
            payload.update(scope=query.scope.replace("-", "_"), slurm_user="alice" if query.scope == "self" else None,
                           slurm_account=query.account_name)
            payload["items"][0].update(array_task_id="0", slurm_account=query.account_name or "personal-alice")
            return JobResult.from_payload(payload, request_id="jobs")
        def show_job(self, job_id, query):
            assert not started.is_set() or release.is_set()
            return self.list_jobs(query)
        def job_allocation(self, job_id, query):
            assert release.is_set()
            payload = deepcopy(site_allocation_payload)
            payload["job"]["array_task_id"] = "0"
            return SiteJobAllocationResult.from_payload(payload, request_id="allocation")
        def job_web_context(self, job_id, query):
            calls.append(job_id)
            started.set()
            assert release.wait(5)
            if transition == "scope":
                raise AuthenticationError("old session failed")
            return JobWebContext.from_payload(sample(), request_id="web")
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await settled(app, pilot)
                await pilot.click("#view-job")
                await settled(app, pilot)
                await pilot.click("#open-job-web")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                app._open_job_in_web()
                app._open_job_in_web()
                app._tick()
                assert calls == ["12345_0"] and not app._pending
                if transition == "mode":
                    await pilot.click("#view-allocation")
                elif transition == "scope":
                    await pilot.press("escape")
                    app.query_one("#scope", Select).value = "org-account"
                    app.query_one("#account", Input).value = "org-example"
                    await pilot.click("#apply")
                elif transition == "tab":
                    app.query_one("#views", TabbedContent).active = "resources"
                    await pilot.pause(.02)
                else:
                    await pilot.press("escape" if transition == "escape" else "f5")
            finally:
                release.set()
            await settled(app, pilot)
            assert opened == [] and calls == ["12345_0"]
            assert not app.paused
            if transition == "scope":
                assert app.results["jobs"].scope == "org_account"
            app._tick()
            await settled(app, pilot)
            assert opened == [] and calls == ["12345_0"]
    asyncio.run(scenario())


@pytest.mark.parametrize("width", [40, 60, 100])
def test_compact_job_actions_shortcuts_palette_and_explicit_copy(width, job_payload, site_allocation_payload, tmp_path):
    calls, opened, copied = [], [], []
    class Client:
        transport = SimpleNamespace(base_url="https://portal.example.org")
        def list_jobs(self, query):
            payload = deepcopy(job_payload)
            payload.update(scope=query.scope.replace("-", "_"), slurm_user="alice" if query.scope == "self" else None,
                           slurm_account=query.account_name)
            payload["items"][0].update(array_task_id="0", slurm_account=query.account_name or "personal-alice")
            return JobResult.from_payload(payload, request_id="jobs")
        def show_job(self, job_id, query):
            return self.list_jobs(query)
        def job_allocation(self, job_id, query):
            calls.append("allocation")
            payload = deepcopy(site_allocation_payload)
            payload["job"]["array_task_id"] = "0"
            return SiteJobAllocationResult.from_payload(payload, request_id="allocation")
        def job_web_context(self, job_id, query):
            calls.append("web")
            return JobWebContext.from_payload(sample(), request_id="web")
    async def palette(app, pilot, command):
        await pilot.press("ctrl+p")
        app.screen.query_one(Input).value = command
        await pilot.pause(.2)
        await pilot.press("enter")
        await settled(app, pilot)
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999)
        app.open_url = opened.append
        native_copy = app.copy_to_clipboard
        def copy_link(value):
            copied.append(value)
            native_copy(value)
        app.copy_to_clipboard = copy_link
        async with app.run_test(size=(width, 24)) as pilot:
            await settled(app, pilot)
            app.query_one("#jobs-table", DataTable).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            for name in ("view-job", "view-allocation", "open-job-web"):
                button = app.query_one(f"#{name}", Button)
                assert button.display and button.region.x >= 0 and button.region.right <= width
            for name in ("account", "partition", "states"):
                field = app.query_one(f"#{name}", Input)
                before = field.value
                field.focus()
                await pilot.press("end", "a", "w")
                assert field.value == before + "aw" and calls == []
                field.value = before
            app.query_one("#jobs-table", DataTable).focus()
            await pilot.press("a")
            await settled(app, pilot)
            assert calls == ["allocation"] and app.job_mode == "allocation"
            await pilot.press("w")
            await settled(app, pilot)
            assert calls == ["allocation", "web"] and len(opened) == 1 and copied == []
            row = app.query_one("#web-link-row", Horizontal)
            copy_button = app.query_one("#copy-web-link", Button)
            assert row.region.height == 1 and copy_button.region.right <= width
            app.save_screenshot(str(tmp_path / f"job-actions-{width}.svg"))
            await pilot.click("#copy-web-link")
            assert copied == opened and app.clipboard == opened[0]
            await palette(app, pilot, "Open in Web")
            assert calls == ["allocation", "web", "web"] and len(opened) == 2 and len(copied) == 1
            await palette(app, pilot, "View allocation")
            assert calls == ["allocation", "web", "web", "allocation"]
            assert app._web_url is None and not row.display
            assert "Copy job Web link" not in [command.title for command in app.get_system_commands(app.screen)]
    asyncio.run(scenario())


def test_quitting_during_web_resolution_does_not_update_unmounted_controls(job_payload):
    started, release = threading.Event(), threading.Event()
    class Client:
        transport = SimpleNamespace(base_url="https://portal.example.org")
        def list_jobs(self, query):
            payload = deepcopy(job_payload)
            payload["items"][0]["array_task_id"] = "0"
            return JobResult.from_payload(payload, request_id="jobs")
        def show_job(self, job_id, query):
            return self.list_jobs(query)
        def job_web_context(self, job_id, query):
            started.set()
            assert release.wait(5)
            return JobWebContext.from_payload(sample(), request_id="web")
    async def scenario():
        app = Workbench(Client(), JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        try:
            async with app.run_test(size=(40, 24)) as pilot:
                await settled(app, pilot)
                await pilot.click("#view-job")
                await settled(app, pilot)
                await pilot.press("w")
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                await pilot.press("ctrl+q")
        finally:
            release.set()
        assert not app.is_running and opened == []
    asyncio.run(scenario())
