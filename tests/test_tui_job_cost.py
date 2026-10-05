from test_tui import choose_compute_scope
"""One selected native job owns detail, allocation and explicit cost inspection."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import json
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent, TabPane

from sai_cli.auth import TokenProvider
from sai_cli.capability import CapabilityProvider
from sai_cli.client import JobQuery, PortalClient
from sai_cli.tui import Workbench
from sai_cli.transport import JsonTransport
from test_capability import _settings
from test_job_web_context import sample as web_sample
from test_site_transport import http_endpoint, issuer
from test_tui import catalog, settled
from test_tui_managed_runs import client_for as managed_client_for


@pytest.fixture(autouse=True)
def local_http(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


def client_for(origin):
    configured = managed_client_for(origin)
    return PortalClient(transport=configured.transport, token_provider=configured.token_provider)


def detail_text(app):
    output = StringIO()
    Console(file=output, width=100, color_system=None).print(app.query_one("#details", Static).content)
    return output.getvalue()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_cost_keeps_one_array_job_updates_state_and_uses_central_price_only(
    tmp_path, monkeypatch, job_cost_payload, site_allocation_payload, language,
):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    priced = deepcopy(job_cost_payload)
    job = priced["items"][0]
    job.update(array_task_id="0", state="S", state_label="suspended")
    estimate = job["running_estimate"]
    estimate.update(job_id_raw="12345_0", state="SUSPENDED", gross_cny="12.34000000",
                    cash_before_credit_cny=None, estimate_status="partial", uncertainty=["cash_price_restricted"])
    site_job = {key: value for key, value in job.items() if key != "running_estimate"}
    site_job.update(state="R", state_label="running")
    native = {"schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a", "scope_type": "self",
              "subject": {"slurm_user": "alice", "slurm_account": None}, "items": [site_job], "etag": "a" * 64,
              "has_more": False, "freshness": {**site_allocation_payload["freshness"], "source": "squeue"}}
    mapping = web_sample()
    mapping.update(job_id="12345_0", submit_time=job["submit_time"], restart_count=None)

    def center(call, count):
        if call["method"] == "POST":
            return issuer(call, count)
        url = urlsplit(call["path"])
        assert call["bearer"] == "Bearer identity-session-token"
        if url.path.endswith("/web-context"):
            query = parse_qs(url.query)
            assert "states" not in query and "partition" not in query
            return 200, mapping
        assert url.path == "/v1/slurm/cli/jobs/12345_0"
        query = parse_qs(url.query)
        assert query["include_estimate"] == ["true"] and "states" not in query and "partition" not in query
        return 200, priced

    def gateway(call, _):
        assert call["bearer"] is None and call["capability"]
        assert "include_estimate" not in call["path"]
        assert call["path"] == "/v1/site-read/jobs"
        return 200, native

    async def scenario(client, calls, reads):
        app = Workbench(client, JobQuery(site_id="site-a", cluster_id="cluster-a", states=("R",)),
                        initial_view="compute", compute_mode="queue", refresh_seconds=999, language=language)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(100, 32)) as pilot:
            await settled(app, pilot)
            assert len(app.query(TabPane)) == 4 and app.job_cost is None
            app.query_one("#compute-table", DataTable).focus()
            await pilot.press("e")
            await settled(app, pilot)
            assert app.selected_job == "12345_0" and app.job_mode == "cost"
            assert app.results["jobs"] is app.job_cost.observation
            assert app.results["jobs"].items[0].values["state"] == "S"
            assert app.job_cost.estimate.values["gross_cny"] == "12.34000000"
            text = detail_text(app)
            assert "12.34 CNY" in text and "12.34000000" not in text
            assert app.t("gross") in text and app.t("cash_restricted") in text
            assert app.t("suspended") in text
            assert not app._presentation().automatic_refresh and not app.check_action("pause", ())
            previous = (len(calls), len(reads))
            app._tick()
            await pilot.press("f6")
            await pilot.pause(.05)
            assert (len(calls), len(reads)) == previous
            for width, height in ((40, 24), (60, 24), (100, 32)):
                await pilot.resize_terminal(width, height)
                await pilot.pause(.05)
                for identifier in ("compute-detail", "compute-resources", "compute-cost", "compute-web"):
                    bounds = app.query_one(f"#{identifier}").region
                    assert 0 <= bounds.x < bounds.right <= width
                app.save_screenshot(str(tmp_path / f"job-cost-{language}-{width}.svg"))
            await pilot.press("w")
            await settled(app, pilot)
            context = json.loads(parse_qs(urlsplit(opened[-1]).fragment.split("?", 1)[1])["job_context"][0])
            assert context["job_id"] == "12345_0" and "/jobs?" in opened[-1] and "run_ref" not in opened[-1]
            estimate.update(gross_cny=None, cash_before_credit_cny=None, price_revision=None,
                            estimate_status="unavailable", uncertainty=["native_usage_unavailable"])
            estimate["resources"].update(resource_type=None, resource_count=None, usage_quantity=None)
            await pilot.press("f5")
            await settled(app, pilot)
            assert app.results["jobs"].items[0].values["state"] == "S"
            assert "12.34" not in detail_text(app) and app.t("unavailable") in detail_text(app)
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.read_view == "jobs" and app.selected_job is None and app.job_cost is None
            assert app.results["jobs"].items[0].values["state"] == "R"
            assert len(reads) == 2

    with http_endpoint(center) as (origin, calls), http_endpoint(gateway) as (site_origin, reads):
        settings = replace(_settings(tmp_path), base_url=origin, cluster_id="cluster-a", site_read_base_url=site_origin)
        transport = JsonTransport(base_url=origin, timeout_seconds=2)
        client = PortalClient(transport=transport,
            token_provider=TokenProvider(settings=settings, transport=transport, environ={"SAI_TOKEN": "identity-session-token"}),
            capability_provider=CapabilityProvider(settings=settings, portal_transport=transport),
            site_transport=JsonTransport(base_url=site_origin, timeout_seconds=2))
        asyncio.run(scenario(client, calls, reads))


@pytest.mark.parametrize("transition", ["detail", "scope", "tab", "escape"])
def test_late_cost_or_denial_cannot_restore_an_old_job_context(job_payload, job_cost_payload, transition):
    started, release = threading.Event(), threading.Event()
    def reply(call, _):
        url = urlsplit(call["path"])
        if parse_qs(url.query).get("include_estimate") == ["true"]:
            started.set()
            assert release.wait(10)
            return (403, {"detail": {"code": "job_cost_read_denied"}}) if transition == "scope" else (200, job_cost_payload)
        if url.path.endswith("resource-catalog"):
            return 200, catalog()
        query = parse_qs(url.query)
        response = deepcopy(job_payload)
        if query.get("scope_type") == ["org_account"]:
            response.update(scope="org_account", slurm_user=None, slurm_account="org-example")
            response["items"][0]["slurm_account"] = "org-example"
        return 200, response

    async def scenario(origin):
        app = Workbench(client_for(origin), JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(100, 32)) as pilot:
            try:
                await settled(app, pilot)
                app.action_view_cost()
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                if transition == "detail": app._inspect_job("detail")
                elif transition == "scope":
                    choose_compute_scope(app, "org:example")
                elif transition == "tab": app.query_one("#views", TabbedContent).active = "resources"
                else: app.action_back()
                await pilot.pause(.02)
            finally:
                release.set()
            await settled(app, pilot)
            assert app.job_cost is None and app.job_mode == ("cost" if transition == "tab" else "detail")
            if transition == "scope": assert app.results["jobs"].scope == "org_account"
            assert app.t("job_cost_denied") not in detail_text(app)
            assert "12.34" not in detail_text(app)
    with http_endpoint(reply) as (origin, _):
        asyncio.run(scenario(origin))


@pytest.mark.parametrize("status", [401, 403])
def test_general_job_denial_clears_cost_and_native_observation(job_cost_payload, status):
    denied = False
    def reply(call, _):
        return (status, {"detail": {"code": "permission_denied"}}) if denied else (200, job_cost_payload)
    async def scenario(origin):
        nonlocal denied
        app = Workbench(client_for(origin), JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.action_view_cost()
            await settled(app, pilot)
            assert app.job_cost is not None
            denied = True
            await pilot.press("f5")
            await settled(app, pilot)
            assert app.job_cost is None and "jobs" not in app.results and not detail_text(app).strip()
    with http_endpoint(reply) as (origin, _):
        asyncio.run(scenario(origin))


def test_tiny_positive_cost_and_usage_never_render_as_zero(job_cost_payload):
    from sai_cli.contracts import JobCostResult
    from sai_cli.tui_views import job_cost_panel
    item = job_cost_payload["items"][0]["running_estimate"]
    item.update(gross_cny="0.00000001", cash_before_credit_cny="0.00000001")
    item["resources"]["usage_quantity"] = "0.00000001"
    for language in ("zh-CN", "en-US"):
        output = StringIO()
        Console(file=output, width=100, color_system=None).print(job_cost_panel(JobCostResult.from_payload(job_cost_payload, request_id="small"), language))
        text = output.getvalue()
        assert text.count("0.00000001 CNY") == 2 and "0.00000001" in text
    item.update(gross_cny="0.00000000", cash_before_credit_cny="0.00000000")
    item["resources"]["usage_quantity"] = "0.00000000"
    output = StringIO()
    Console(file=output, width=100).print(job_cost_panel(JobCostResult.from_payload(job_cost_payload, request_id="zero")))
    assert output.getvalue().count("0.00 CNY") == 2 and "<0.01" not in output.getvalue()
