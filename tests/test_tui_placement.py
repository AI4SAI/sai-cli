import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, Static, TabbedContent

from sai_cli.client import JobQuery
from sai_cli.contracts import JobResult
from sai_cli.errors import AuthenticationError, ForbiddenError, UnavailableError
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.site_placement import SiteJobPlacementResult
from sai_cli.tui import Workbench
from sai_cli.tui_views import placement_panel
from test_site_placement import sample
from test_tui import settled
from test_tui_allocation import detail_text


class Client:
    def __init__(self, job_payload):
        self.document = sample()
        self.jobs = deepcopy(job_payload)
        self.jobs["items"] = [self.document["allocation"]["job"]]
        self.placement_calls = 0
        self.error = None
        self.block = None

    def list_jobs(self, query):
        return JobResult.from_payload(self.jobs, request_id="jobs")

    def job_allocation(self, identifier, query):
        return SiteJobAllocationResult.from_payload(self.document["allocation"], request_id="allocation")

    def job_placement(self, identifier, query):
        self.placement_calls += 1
        if self.block is not None:
            started, release = self.block
            started.set()
            assert release.wait(5)
        if self.error is not None:
            raise self.error
        return SiteJobPlacementResult.from_payload(self.document, request_id="placement")


def clock(monkeypatch):
    now = [datetime.fromisoformat("2026-09-23T00:00:02+00:00").timestamp()]
    monkeypatch.setattr("sai_cli.tui.time", SimpleNamespace(time=lambda: now[0]))
    return now


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_registered_location_panel_has_readable_units_and_verification_time(language, width):
    output = StringIO()
    result = SiteJobPlacementResult.from_payload(sample(), request_id="panel")
    Console(file=output, width=width, color_system=None).print(placement_panel(result, language))
    text = output.getvalue()
    for expected in ("node-a", "Rack A", "U12", "4U", "2026-09-22T20:00:00Z",
                     "核对时间" if language == "zh-CN" else "Verified"):
        assert expected in text


def test_location_explicit_read_uses_its_allocation_then_expires_without_network(job_payload, monkeypatch):
    now = clock(monkeypatch)
    client = Client(job_payload)
    async def scenario():
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert app.query_one("#compute-placement", Button).disabled and client.placement_calls == 0
            app.action_view_allocation()
            await settled(app, pilot)
            assert client.placement_calls == 0 and not app.query_one("#compute-placement", Button).disabled
            client.document["allocation"]["restart_count"] = 7
            await pilot.pause(.05)
            await pilot.click("#compute-placement")
            await settled(app, pilot)
            assert app.placement_result is not None and client.placement_calls == 1
            assert app.results["jobs"].restart_count == 7
            assert "Rack A" in detail_text(app)
            app._tick()
            assert not app._pending and client.placement_calls == 1
            now[0] = datetime.fromisoformat("2026-09-24T00:00:00+00:00").timestamp()
            app._tick()
            assert app.placement_result is None and client.placement_calls == 1
            assert "Rack A" not in detail_text(app) and app.results["jobs"].restart_count == 7
            assert "Registration expired" in str(app.query_one("#status", Static).render())
    asyncio.run(scenario())


@pytest.mark.parametrize("error,keeps_allocation", [
    (UnavailableError("unavailable"), True), (ForbiddenError("denied"), False), (AuthenticationError("expired"), False),
])
def test_location_failure_clears_registration_and_respects_authorization(job_payload, monkeypatch, error, keeps_allocation):
    clock(monkeypatch)
    client = Client(job_payload)
    async def scenario():
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.action_view_allocation()
            await settled(app, pilot)
            app.action_view_placement()
            await settled(app, pilot)
            previous = app.results["jobs"]
            client.error = error
            app.action_refresh()
            assert app.placement_result is None and "Rack A" not in detail_text(app)
            await settled(app, pilot)
            assert app.placement_result is None
            if keeps_allocation:
                assert app.results["jobs"] is previous
            else:
                assert "jobs" not in app.results
    asyncio.run(scenario())


def test_late_location_response_does_not_survive_context_change(job_payload, monkeypatch):
    clock(monkeypatch)
    client = Client(job_payload)
    started, release = threading.Event(), threading.Event()
    client.block = (started, release)
    async def scenario():
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.action_view_allocation()
            await settled(app, pilot)
            app.action_view_placement()
            try:
                for _ in range(80):
                    if started.is_set(): break
                    await pilot.pause(.02)
                assert started.is_set()
                app.query_one("#views", TabbedContent).active = "storage"
                await pilot.pause(.02)
            finally:
                release.set()
            await settled(app, pilot)
            assert app.placement_result is None and "jobs" not in app.results
            assert app._placement_timer is None
            assert "Rack A" not in detail_text(app)
    asyncio.run(scenario())


@pytest.mark.parametrize("first_expiry", ["registration", "inventory"])
def test_location_expires_at_real_deadline_independently_of_refresh_interval(job_payload, first_expiry):
    class TimedClient(Client):
        def job_placement(self, identifier, query):
            now = datetime.now(timezone.utc)
            def stamp(seconds): return (now + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
            self.document["allocation"]["freshness"]["observed_at"] = stamp(-10)
            self.document["inventory"].update(published_at=stamp(-20), expires_at=stamp(.7 if first_expiry == "inventory" else 3600))
            self.document["nodes"][0]["registration"].update(verified_at=stamp(-30), valid_until=stamp(.7))
            return super().job_placement(identifier, query)
    client = TimedClient(job_payload)
    async def scenario():
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="compute", compute_mode="queue", refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app.action_view_allocation()
            await settled(app, pilot)
            app.action_view_placement()
            await settled(app, pilot)
            allocation = app.results["jobs"]
            assert app.placement_result is not None and app._placement_timer is not None
            await pilot.pause(.9)
            assert app.placement_result is None and app._placement_timer is None
            assert app.results["jobs"] is allocation and client.placement_calls == 1
            assert "Rack A" not in detail_text(app)
            assert "Registration expired" in str(app.query_one("#status", Static).render())
    asyncio.run(scenario())
