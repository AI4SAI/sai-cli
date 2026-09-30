"""The visible workbench actions and evidence follow the current interaction."""
import asyncio
from copy import deepcopy
from io import StringIO
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, DataTable, Input, OptionList, Select, Static, TabbedContent
from rich.console import Console

from sai_cli.client import JobQuery, PortalClient
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.tui import Workbench
from test_managed_runs_contract import sample
from test_managed_workspaces import sample as workspace_sample
from test_overview import sample as overview_sample
from test_site_transport import http_endpoint
from test_tui import catalog, settled, storage_sample, storage_workspaces_sample
from test_tui_managed_runs import click, client_for


LONG_TASK_TITLE = "train-" + "超长任务标题-" * 18 + "final.py"


def visible_text(app):
    root = ET.fromstring(app.export_screenshot())
    return "\n".join("".join(node.itertext()) for node in root.iter("{http://www.w3.org/2000/svg}text"))


@pytest.fixture
def workbench_http(job_payload, running_estimate_payload, monkeypatch, request):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost,::1")
    options = getattr(request, "param", {})

    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("/storage/workspaces"):
            return 200, storage_workspaces_sample()
        if path.endswith("resource-catalog"):
            data = catalog()
            data["compute"][0].update(title="Evidence GPU", summary="Catalog evidence", scenarios=["Research"])
            return 200, data
        if path.endswith("/workspaces"):
            return 200, workspace_sample()
        if path.endswith("/running-estimates"):
            if options.get("empty_usage"):
                return 200, {**running_estimate_payload, "items": [], "count": 0}
            return 200, running_estimate_payload
        if path.endswith("/quota-summary"):
            return 200, storage_sample("project:storage-example")
        if path.endswith("/overview"):
            return 200, overview_sample()
        if path.endswith("/runs"):
            data = sample("list")
            if "title" in options:
                data["items"][0]["title"] = options["title"]
            return 200, data
        if path.endswith("/artifacts"):
            return 200, sample("artifacts")
        if path.endswith("/logs"):
            return 200, sample("log")
        if path.endswith("/run-example-1"):
            data = sample("detail")
            if "title" in options:
                data["run"]["title"] = options["title"]
            return 200, data
        return 200, job_payload
    with http_endpoint(reply) as (origin, calls):
        configured = client_for(origin)
        yield PortalClient(
            transport=configured.transport,
            token_provider=configured.token_provider,
        ), calls


@pytest.fixture
def error_workbench_http(job_payload, running_estimate_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost,::1")
    state = {"status": 200}

    def reply(call, _):
        path = urlsplit(call["path"]).path
        if path.endswith("/running-estimates") and state["status"] != 200:
            return state["status"], {
                "detail": {
                    "code": "private-source-error",
                    "message": "private provider detail",
                }
            }
        if path.endswith("/running-estimates"):
            return 200, running_estimate_payload
        if path.endswith("resource-catalog"):
            return 200, catalog()
        return 200, job_payload

    with http_endpoint(reply) as (origin, calls):
        configured = client_for(origin)
        yield (
            PortalClient(
                transport=configured.transport,
                token_provider=configured.token_provider,
            ),
            calls,
            state,
        )


async def enter_detail(app, pilot, view):
    app.query_one("#views", TabbedContent).active = view
    await settled(app, pilot)
    app.query_one(f"#{view}-table", DataTable).focus()
    await pilot.press("enter")
    await settled(app, pilot)


def test_retained_task_selection_does_not_advertise_back_in_another_view(workbench_http):
    client, _calls = workbench_http
    async def scenario():
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="tasks",
                        tasks_workspace_key="project:project-example", refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await enter_detail(app, pilot, "tasks")
            assert app.selected_run == "run-example-1"
            for view in ("overview", "resources", "jobs", "usage"):
                app.query_one("#views", TabbedContent).active = view
                await settled(app, pilot)
                app.query_one("#views").focus()
                await pilot.pause(.03)
                assert app.check_action("back", ()) is False, view
                assert "escape" not in app.screen.active_bindings, view
                assert not any(
                    command.callback == app.action_back
                    for command in app.get_system_commands(app.screen)
                ), view
    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["files", "allocation", "estimate", "resource"])
def test_paused_inspection_has_no_fake_resume_and_f6_preserves_evidence(workbench_http, site_allocation_payload, phase):
    client, calls = workbench_http
    if phase == "allocation":
        client.job_allocation = lambda *_: SiteJobAllocationResult.from_payload(
            deepcopy(site_allocation_payload), request_id="allocation",
        )
    async def scenario():
        initial = {
            "files": "tasks",
            "allocation": "jobs",
            "estimate": "usage",
            "resource": "resources",
        }[phase]
        app = Workbench(
            client,
            JobQuery(site_id="site-a"),
            initial_view=initial,
            tasks_workspace_key="project:project-example",
            refresh_seconds=999,
        )
        app.open_url = lambda _: None
        async with app.run_test(size=(60, 18)) as pilot:
            await enter_detail(app, pilot, initial)
            if phase == "files":
                await click(app, pilot, "#task-files")
                app.query_one("#task-artifacts", OptionList).focus()
                await pilot.press("home", "enter", "w")
            elif phase == "allocation":
                app.action_view_allocation()
                await settled(app, pilot)
            elif phase == "resource":
                await pilot.press("w")
            await pilot.pause(.05)
            before = (
                len(calls), app.selected_job, app.selected_run,
                app.selected_resource, app.selected_estimate,
                app.task_file_page, app.selected_artifact, app._web_url,
            )
            assert app.check_action("pause", ()) is False
            assert "f6" not in app.screen.active_bindings
            assert not any(command.callback == app.action_pause for command in app.get_system_commands(app.screen))
            await pilot.press("f6", "f6")
            await settled(app, pilot)
            after = (
                len(calls), app.selected_job, app.selected_run,
                app.selected_resource, app.selected_estimate,
                app.task_file_page, app.selected_artifact, app._web_url,
            )
            assert after == before
    asyncio.run(scenario())


@pytest.mark.parametrize("width,height", [(40, 24), (60, 18), (100, 32)])
@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_each_view_gives_primary_evidence_a_readable_viewport(workbench_http, tmp_path, width, height, language):
    client, _calls = workbench_http
    async def scenario():
        app = Workbench(
            client,
            JobQuery(site_id="site-a"),
            initial_view="overview",
            language=language,
            tasks_workspace_key="project:project-example",
            storage_workspace_key="project:storage-example",
            refresh_seconds=999,
        )
        async with app.run_test(size=(width, height)) as pilot:
            for view in ("overview", "resources", "jobs", "usage", "storage", "tasks"):
                app.query_one("#views", TabbedContent).active = view
                await settled(app, pilot)
                if view in {"resources", "jobs", "usage", "tasks"}:
                    app.query_one(f"#{view}-table", DataTable).focus()
                    await pilot.press("enter")
                    await settled(app, pilot)
                if view == "tasks":
                    await click(app, pilot, "#task-files")
                    region_widget = app.query_one("#task-artifacts", OptionList)
                    marker = "energy result.txt"
                elif view == "overview":
                    region_widget = app.query_one("#overview-summary").parent
                    marker = "1,280.50"
                elif view == "storage":
                    region_widget = app.query_one("#storage-scroll")
                    marker = "1.00000000"
                else:
                    region_widget = app.query_one("#details-scroll")
                    marker = {
                        "resources": "Catalog evidence",
                        "jobs": "12345",
                        "usage": "12345",
                    }[view]
                await pilot.pause(.05)
                region = region_widget.region
                assert region_widget.display and region.height >= max(6, height // 3), (view, region)
                assert 0 <= region.y < region.bottom <= height - 1, (view, region)
                assert 0 <= region.x < region.right <= width, (view, region)
                assert marker.replace(" ", "") in "".join(visible_text(app).split()), view
                app.save_screenshot(str(tmp_path / f"evidence-{view}-{language}-{width}x{height}.svg"))
    asyncio.run(scenario())


def test_resource_escape_returns_to_catalog_without_reading_and_labels_follow_candidate(workbench_http):
    client, calls = workbench_http
    async def scenario():
        app = Workbench(
            client, JobQuery(site_id="site-a"), initial_view="resources", refresh_seconds=999,
        )
        app.open_url = lambda _: None
        async with app.run_test(size=(40, 24)) as pilot:
            await enter_detail(app, pilot, "resources")
            await pilot.press("c", "w")
            await pilot.pause(.05)
            assert app.compared == ["gpu-standard"] and app._web_url is not None
            assert "remove" in app.screen.active_bindings["c"].binding.description.lower()
            assert "prepar" in app.screen.active_bindings["w"].binding.description.lower()
            commands = list(app.get_system_commands(app.screen))
            assert any("remove" in command.title.lower() for command in commands)
            before = len(calls)
            app.query_one("#details-scroll").focus()
            await pilot.press("escape")
            await pilot.pause(.05)
            assert app.selected_resource is None and app._web_url is None
            assert len(calls) == before
            assert app.check_action("back", ()) is False
    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["jobs_list", "jobs_detail", "task_detail"])
def test_pause_only_changes_automatic_refresh_in_supported_phase(workbench_http, phase):
    client, calls = workbench_http
    async def scenario():
        view = "tasks" if phase == "task_detail" else "jobs"
        app = Workbench(
            client, JobQuery(site_id="site-a"), initial_view=view,
            tasks_workspace_key="project:project-example", refresh_seconds=999,
        )
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            if phase != "jobs_list":
                await enter_detail(app, pilot, view)
                app.query_one("#details-scroll").focus()
            else:
                app.query_one(f"#{view}-table", DataTable).focus()
            assert app.check_action("pause", ()) is True
            before = len(calls)
            await pilot.press("f6")
            app._tick()
            await pilot.pause(.05)
            assert app.paused and len(calls) == before
            await pilot.press("f6")
            await settled(app, pilot)
            assert not app.paused and len(calls) == before + 1
    asyncio.run(scenario())


def test_input_letters_and_escape_remain_owned_by_editing_widget(workbench_http):
    client, calls = workbench_http
    async def scenario():
        app = Workbench(
            client, JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999,
        )
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            for name in ("account", "partition", "states"):
                field = app.query_one("#" + name, Input)
                assert field.display and field.parent.display
                field.focus()
                before = field.value
                read_count = len(calls)
                await pilot.press("end", "c", "a", "w", "escape")
                await pilot.pause(.05)
                assert field.value == before + "caw" and len(calls) == read_count
                assert app.selected_job is None and app.view == "jobs"
                for key in ("a", "c", "w", "escape"):
                    binding = app.screen.active_bindings.get(key)
                    assert binding is None or binding.node is not app
                field.value = before
            selector = app.query_one("#scope", Select)
            assert selector.display and selector.parent.display
            selector.focus()
            before = selector.value
            await pilot.press("enter")
            await pilot.pause(.05)
            assert selector.expanded
            await pilot.press("escape")
            await pilot.pause(.05)
            assert not selector.expanded and selector.value == before
            assert app.selected_job is None
    asyncio.run(scenario())


def test_empty_jobs_buttons_keys_and_palette_agree(job_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    payload = deepcopy(job_payload)
    payload.update(items=[], count=0)

    async def scenario(client):
        app = Workbench(
            client, JobQuery(site_id="site-a"), initial_view="jobs", refresh_seconds=999,
        )
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            assert app.query_one("#view-job", Button).disabled
            assert app.query_one("#view-allocation", Button).disabled
            assert "a" not in app.screen.active_bindings
            assert not any(
                command.callback == app.action_view_allocation
                for command in app.get_system_commands(app.screen)
            )

    with http_endpoint(lambda *_: (200, payload)) as (origin, _):
        configured = client_for(origin)
        client = PortalClient(
            transport=configured.transport, token_provider=configured.token_provider,
        )
        asyncio.run(scenario(client))


@pytest.mark.parametrize("status", [403, 503])
def test_usage_error_is_visible_and_f5_recovers_from_real_http(
    error_workbench_http,
    status,
):
    client, calls, state = error_workbench_http

    async def scenario():
        app = Workbench(
            client,
            JobQuery(site_id="site-a"),
            initial_view="jobs",
            refresh_seconds=999,
        )
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            jobs = app.results["jobs"]
            await enter_detail(app, pilot, "usage")
            assert app.selected_estimate is not None
            state["status"] = status
            await pilot.press("f5")
            await settled(app, pilot)
            assert "usage" not in app.results
            assert app.results["jobs"] is jobs
            assert app.selected_estimate is None
            assert str(app.query_one("#details", Static).render()) == ""
            assert app.query_one("#usage-notice", Static).display
            notice = "".join(visible_text(app).split())
            message = app.t("access_denied" if status == 403 else "read_failed")
            assert "".join(message.split()) in notice and "F5" in notice
            assert "privateproviderdetail" not in notice
            failed_calls = len(calls)
            app._tick()
            await pilot.pause(.05)
            assert len(calls) == failed_calls

            state["status"] = 200
            await pilot.press("f5")
            await settled(app, pilot)
            assert "usage" in app.results
            assert app.query_one("#usage-notice", Static).display is False
            assert app.results["jobs"] is jobs
            assert app.query_one("#usage-table", DataTable).row_count > 0
            assert message not in str(app.query_one("#status", Static).render())
            assert len(calls) == failed_calls + 1

    asyncio.run(scenario())


@pytest.mark.parametrize("workbench_http", [{"empty_usage": True}], indirect=True)
def test_empty_usage_has_bounded_notice_and_no_selection_prompt(workbench_http):
    client, calls = workbench_http

    async def scenario():
        app = Workbench(
            client,
            JobQuery(site_id="site-a"),
            initial_view="usage",
            refresh_seconds=999,
        )
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert app.query_one("#usage-table", DataTable).row_count == 0
            assert app.query_one("#usage-notice", Static).display
            visible = "".join(visible_text(app).split())
            assert "".join(app.t("empty_estimates").split()) in visible
            assert "".join(app.t("usage_choose").split()) not in visible
            assert "escape" not in app.screen.active_bindings
            assert len(calls) == 1
            assert calls[0]["method"] == "GET"
            assert urlsplit(calls[0]["path"]).path.endswith("/running-estimates")

    asyncio.run(scenario())


@pytest.mark.parametrize("workbench_http", [{"title": LONG_TASK_TITLE}], indirect=True)
def test_long_task_title_wraps_in_full_detail_on_a_short_screen(workbench_http):
    client, calls = workbench_http

    async def scenario():
        app = Workbench(
            client,
            JobQuery(site_id="site-a"),
            initial_view="tasks",
            tasks_workspace_key="project:project-example",
            refresh_seconds=999,
        )
        async with app.run_test(size=(40, 18)) as pilot:
            await enter_detail(app, pilot, "tasks")
            result = app.results["tasks"]
            assert result.values["run"]["title"] == LONG_TASK_TITLE
            await pilot.pause(.05)
            rendered = StringIO()
            Console(file=rendered, width=40, color_system=None).print(
                app.query_one("#details", Static).content,
            )
            text = rendered.getvalue()
            assert LONG_TASK_TITLE in "".join(text.split())
            assert "…" not in text
            assert app.query_one("#object-heading").region.height == 1
            detail = app.query_one("#details-scroll")
            assert detail.display and detail.region.height >= 6
            assert 0 <= detail.region.y < detail.region.bottom <= 17
            detail.scroll_end(animate=False)
            await pilot.pause(.05)
            assert result.values["run"]["last_observed_at"] in "".join(visible_text(app).split())
            assert len(calls) == 3 and all(call["method"] == "GET" for call in calls)
            assert [urlsplit(call["path"]).path for call in calls] == [
                "/v1/compute/cli/workspaces", "/v1/compute/cli/runs", "/v1/compute/cli/runs/run-example-1"]
            assert all(parse_qs(urlsplit(call["path"]).query)["workspace_key"] == ["project:project-example"] for call in calls)

    asyncio.run(scenario())
