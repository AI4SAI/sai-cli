"""Placement validity expires independently of refresh and modal interaction."""
import asyncio
from datetime import datetime, timedelta, timezone
from io import StringIO
import json

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Static

from sai_cli.client import JobQuery
from sai_cli.managed_runs import ManagedRunDetail
from sai_cli.run_placement import ManagedRunPlacement
from sai_cli.site_placement import SiteJobPlacementResult
from sai_cli.workbench import Work, Workbench
from test_managed_runs_contract import sample as run_sample
from test_site_placement import sample
from test_site_transport import http_endpoint
from test_workbench_flow import ROOT, ResearchHTTP, client, settled


def observation(kind="native", *, seconds=.45, inventory_first=False, job_id=None):
    if kind == "run":
        wrapper = json.loads((ROOT / "contracts/managed-run-placement/v1/allocated.sample.json").read_text())
        data = wrapper["placement"]
    else:
        data = sample()
    now = datetime.now(timezone.utc)

    def stamp(delta):
        return (now + timedelta(seconds=delta)).isoformat().replace("+00:00", "Z")

    data["allocation"]["freshness"]["observed_at"] = stamp(-10)
    data["inventory"].update(published_at=stamp(-20), expires_at=stamp(seconds if inventory_first else 3600))
    for node in data["nodes"]:
        if inventory_first:
            node.update(status="unmapped", registration=None)
        elif node["registration"] is not None:
            node["registration"].update(verified_at=stamp(-30), valid_until=stamp(seconds))
    if job_id is not None:
        data["allocation"]["job"]["job_id"] = job_id
    if kind == "run":
        return ManagedRunPlacement.from_payload(wrapper, site_id=wrapper["site_id"],
            workspace_key=wrapper["workspace_key"], run_ref=wrapper["run_ref"], request_id="expiry")
    return SiteJobPlacementResult.from_payload(data, request_id="expiry")


def show_placement(app, result):
    if isinstance(result, ManagedRunPlacement):
        data = run_sample("detail")
        app.detail = ManagedRunDetail.from_payload(data, workspace_key=data["workspace_key"], site_id=data["site_id"],
            run_ref=data["run"]["run_ref"], request_id="run")
        app.selected = Work("run", data["run"]["run_ref"], "Research result", data["workspace_key"])
    else:
        app.detail = result.allocation
        app.selected = Work("native", result.allocation.job.canonical_id, "Research result")
    app.mode = "placement"
    app._accept(result)


def body(app):
    output = StringIO()
    Console(file=output, width=80, color_system=None).print(app.query_one("#work-evidence", Static).content)
    return output.getvalue()


@pytest.mark.parametrize("kind", ["native", "run"])
@pytest.mark.parametrize("modal", [False, True])
def test_registration_deadline_expires_once_even_inside_a_modal(job_payload, kind, modal):
    async def scenario(origin, calls):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), language="en-US", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            result = observation(kind)
            allocation = result.placement.allocation if kind == "run" else result.allocation
            show_placement(app, result)
            assert app._placement_timer is not None and "Rack A" in body(app)
            reads = len(calls)
            if modal:
                app.action_more()
                await pilot.pause(.03)
                assert app.screen is not app.default_screen
            await pilot.pause(.6)
            assert app.result is allocation and app._placement_timer is None and len(calls) == reads
            assert "Rack A" not in body(app)
            assert app.t("placement_expired") in str(app.query_one("#work-status", Static).content)
            if modal:
                assert app.screen is not app.default_screen
                await pilot.press("escape")
                assert app.result is allocation
            app._render()
            assert app.t("placement_expired") in str(app.query_one("#work-status", Static).content)

    with http_endpoint(ResearchHTTP(job_payload)) as (origin, calls):
        asyncio.run(scenario(origin, calls))


def test_inventory_deadline_expires_without_a_registered_node(job_payload):
    async def scenario(origin, calls):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            result = observation(inventory_first=True)
            show_placement(app, result)
            assert app._placement_timer is not None
            reads = len(calls)
            await pilot.pause(.6)
            assert app.result is result.allocation and app._placement_timer is None and len(calls) == reads

    with http_endpoint(ResearchHTTP(job_payload)) as (origin, calls):
        asyncio.run(scenario(origin, calls))


def test_navigation_and_replacement_stop_old_timer_and_reject_queued_callbacks(job_payload, monkeypatch):
    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            callbacks = []
            schedule = app.set_timer

            def capture(delay, callback, **kwargs):
                callbacks.append(callback)
                return schedule(delay, callback, **kwargs)

            monkeypatch.setattr(app, "set_timer", capture)
            first = observation(seconds=30)
            show_placement(app, first)
            old_callback = callbacks[-1]
            app.action_back()
            assert app._placement_timer is None and app.result is None
            old_callback()
            assert app.result is None
            await settled(app, pilot)
            home = app.result
            old_callback()
            assert app.result is home and app.mode == "home"
            next_result = observation(seconds=30, job_id="67890")
            show_placement(app, next_result)
            current_callback = callbacks[-1]
            replacement = observation(seconds=30, job_id="98765")
            show_placement(app, replacement)
            current_timer = app._placement_timer
            old_callback()
            current_callback()
            assert app.result is replacement and app._placement_timer is current_timer
            assert app.selected.reference == replacement.allocation.job.canonical_id
            assert not app._placement_expired
        assert app._placement_timer is None

    with http_endpoint(ResearchHTTP(job_payload)) as (origin, _):
        asyncio.run(scenario(origin))
