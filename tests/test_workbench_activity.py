"""One work item keeps live state and results across the two authorized readers."""
import asyncio
from copy import deepcopy
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
pytest.importorskip("textual")
from textual.widgets import OptionList, Static

from sai_cli.auth import TokenLease
from sai_cli.capability import CapabilityLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.transport import JsonTransport
from sai_cli.workbench import Workbench
from test_run_activity import linked_documents
from test_site_transport import http_endpoint
from test_workbench_flow import ResearchHTTP, select, settled


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("outside_history", [False, True])
def test_one_work_keeps_live_state_and_results_without_scope_setup(job_payload, language, outside_history, tmp_path):
    history = ResearchHTTP(job_payload)
    detail, native = linked_documents(job_payload)
    reference = "12345678-abcd-4321-abcd-123456789012" if outside_history else "run-example-1"
    detail["run"]["run_ref"] = reference
    if outside_history:
        native["items"][0]["run_ref"] = reference
    completed = False
    native_error = False

    def reply(call, count):
        from urllib.parse import parse_qs
        path = urlsplit(call["path"]).path
        if path.startswith("/v1/site-read/jobs"):
            assert call["bearer"] is None and call["capability"] == "fixture-capability"
            if native_error:
                return 503, {"detail": {"code": "site_read_source_unavailable"}}
            if completed:
                return 404, {"detail": {"code": "job_not_found"}}
            payload = deepcopy(native)
            payload["freshness"]["source"] = "scontrol" if path.endswith("/12345") else "squeue"
            return 200, payload
        args = parse_qs(urlsplit(call["path"]).query)
        if path == "/v1/compute/cli/my-runs" and "run_refs" in args:
            assert args["run_refs"] == [reference] and args["limit"] == ["100"]
            assert call["bearer"] == "Bearer fixture-token" and call["capability"] is None
            _, value = history({**call, "path": "/v1/compute/cli/my-runs?site_id=site-a"}, count)
            value["items"] = [{**value["items"][0], **detail["run"]}]
            return 200, value
        if outside_history and path.endswith("/runs/" + reference):
            _, value = history({**call, "path": call["path"].replace(reference, "run-example-1")}, count)
            status = 200
        else:
            status, value = history(call, count)
        if path == "/v1/compute/cli/my-runs":
            if outside_history:
                value["items"] = value["items"][1:]
            else:
                value["items"][0].update(detail["run"])
                if completed:
                    value["items"][0].update(status="completed", finished_at="2026-07-31T02:00:00Z")
        elif path.endswith("/runs/" + reference):
            value["run"] = deepcopy(detail["run"])
            if completed:
                value["run"].update(status="completed", finished_at="2026-07-31T02:00:00Z")
        return status, value

    async def scenario(origin, calls):
        nonlocal completed, native_error
        transport = JsonTransport(base_url=origin, timeout_seconds=3)
        capabilities = SimpleNamespace(get=lambda **kwargs: CapabilityLease(
            "fixture-capability", int(time.time()) + 60, "issued", "fixture-key"))
        reader = PortalClient(transport=transport, site_transport=transport, capability_provider=capabilities,
            token_provider=SimpleNamespace(get=lambda: TokenLease("fixture-token", None, "environment")))
        app = Workbench(reader, JobQuery(site_id="site-a", cluster_id="cluster-a"), language=language, refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert set(app.home_items) == {"run:" + reference, "run:run-second"}
            assert len(calls) == 2 + int(outside_history)
            assert app.home_items["run:" + reference].state == "R"
            app.save_screenshot(str(tmp_path / f"linked-home-{language}.svg"))
            await select(app, pilot, "run:" + reference)
            assert app.mode == "run" and app.selected.state == "R"
            assert app.detail.values["run"]["status"] == "queued"
            assert app.t("running") in str(app.query_one("#work-context", Static).content)
            assert "01:00:00" in str(app.query_one("#work-evidence", Static).content)
            assert len(calls) == 4 + int(outside_history)
            native_error = True
            app.action_refresh()
            await settled(app, pilot)
            assert app.selected.reference == reference and app.mode == "run"
            assert app.t("live_failed") in str(app.query_one("#work-evidence", Static).content)
            assert app.t("queued") in str(app.query_one("#work-context", Static).content)
            failed_count = len(calls)
            app._tick()
            await pilot.pause(.05)
            assert len(calls) == failed_count
            # Finished results remain usable while the scheduler read is unavailable.
            completed = True
            app.action_refresh()
            await settled(app, pilot)
            assert app.mode == "files" and app.detail.values["run"]["status"] == "completed"
            assert not any(urlsplit(call["path"]).path.startswith("/v1/site-read/") for call in calls[failed_count:])
            app.query_one("#work-files", OptionList).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.mode == "content" and app.selected.workspace == "project:first"
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "files"
    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(origin, calls))
    assert all(call["method"] == "GET" for call in calls)
