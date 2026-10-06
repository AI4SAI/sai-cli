"""Researcher journeys over the actual bounded HTTP client."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, Input, OptionList, Static

from sai_cli.auth import TokenLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.errors import AuthenticationError
from sai_cli.oidc import DeviceAuthorization, DeviceTokenResult
from sai_cli.transport import JsonTransport
from sai_cli.workbench import Workbench
from test_artifact_download import ARTIFACT, VERSION, RANGE_BYTES, binary_endpoint, grant, response
from test_managed_runs_contract import sample
from test_site_transport import http_endpoint


ROOT = Path(__file__).resolve().parents[1]


async def settled(app, pilot):
    for _ in range(200):
        await pilot.pause(.02)
        if not app._reading and app._pending is None:
            await pilot.pause(.05)
            return
    raise AssertionError("workbench reader did not settle")


def client(origin):
    return PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=3),
        token_provider=SimpleNamespace(get=lambda: TokenLease("fixture-token", None, "environment")))


class ResearchHTTP:
    def __init__(self, job_payload):
        self.jobs = deepcopy(job_payload)
        self.status = "completed"
        self.empty = False
        self.fail_content = self.fail_history = 0
        self.fail_code = "run_file_read_denied"
        self.block = False
        self.started, self.release = threading.Event(), threading.Event()
        self.site = None
        self.binary = False
        self.download_size = 0
        self.content_status = "available"
        self.history_pages = False
        self.scope = "self"
        self.storage_denied = False

    def __call__(self, call, _):
        url = urlsplit(call["path"])
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        assert call["bearer"] == "Bearer fixture-token" and call["capability"] is None
        if url.path == "/v1/slurm/jobs":
            assert query["scope_type"] == self.scope
            value = deepcopy(self.jobs)
            if self.scope != "self":
                value.update(scope=self.scope, slurm_user=None, slurm_account="org-example", visibility_role="owner")
                value["items"][0]["slurm_account"] = "org-example"
            if self.empty:
                value.update(items=[], count=0)
            return 200, value
        if url.path == "/v1/slurm/jobs/12345":
            assert "partition" not in query and "states" not in query
            value = deepcopy(self.jobs)
            value["freshness"]["source"] = "scontrol"
            return 200, value
        if url.path == "/v1/compute/cli/my-runs":
            assert set(query) <= {"site_id", "limit", "cursor"}
            if self.fail_history:
                return self.fail_history, {"detail": {"code": "run_read_unavailable"}}
            row = sample("detail")["run"]
            row.update(status=self.status, title="Energy calculation", workspace_key="project:first",
                       workspace_label="Catalysis", organization_label="Research")
            rows = [row, {**row, "run_ref": "run-second", "workspace_key": "org:second", "workspace_label": "Spectra"}]
            if self.history_pages and "cursor" in query:
                rows = [{**row, "run_ref": "run-third"}]
            return 200, {"schema_version": "compute.my-runs/v1", "site_id": "site-a", "source": "portal_run_receipts",
                "queried_at": "2030-01-01T00:06:00Z", "items": [] if self.empty else rows,
                "has_more": self.history_pages and "cursor" not in query,
                "next_cursor": "run-second" if self.history_pages and "cursor" not in query else None}
        if url.path == "/v1/compute/cli/workspaces":
            value = json.loads((ROOT / "contracts/managed-workspaces/v1/sample.json").read_text())
            value["items"] = [{"workspace_key": "org:second", "label": "Spectra", "organization_label": None}]
            return 200, value
        if url.path == "/v1/compute/cli/runs":
            assert query["workspace_key"] == "org:second"
            value = sample("list")
            value["items"][0].update(run_ref="run-second", status=self.status)
            value["workspace_key"] = "org:second"
            return 200, value
        if url.path.endswith("/resource-catalog"):
            value = json.loads((ROOT / "contracts/site-resource-catalog/v1/catalog.json").read_text())
            value["site_id"] = "site-a"
            return 200, value
        if url.path.endswith("/storage/workspaces"):
            return 200, json.loads((ROOT / "contracts/storage-workspaces/v1/sample.json").read_text())
        if url.path.endswith("/storage/quota-summary"):
            if self.storage_denied:
                return 403, {"detail": {"code": "storage_read_denied"}}
            value = json.loads((ROOT / "contracts/storage-quota-summary/v1/sample.json").read_text())
            value["workspace_key"] = query["workspace_key"]
            return 200, value
        parts = url.path.split("/")
        run = parts[5]
        workspace = "org:second" if run == "run-second" else "project:first"
        if call["method"] == "POST":
            assert call["body"]["workspace_key"] == workspace
            return 200, grant(self.site, self.download_size, workspace_key=workspace, run_ref=run)
        assert query["workspace_key"] == workspace
        if url.path.endswith("/billing"):
            value = json.loads((ROOT / "contracts/managed-run-cost/v1/settled.sample.json").read_text())
        elif url.path.endswith("/content"):
            if self.block:
                self.started.set()
                assert self.release.wait(6)
            if self.fail_content:
                return self.fail_content, {"detail": {"code": self.fail_code, "message": "private raw text"}}
            value = json.loads((ROOT / "contracts/managed-run-content/v1/available.sample.json").read_text())
            cursor = query.get("cursor")
            content = "second output page" if cursor else "first output page"
            size = len("first output pagesecond output page")
            offset = int(cursor.split(":")[1]) if cursor else 0
            end = offset + len(content)
            value.update(cursor=cursor, content=content, offset=offset, next_offset=end, bytes_read=len(content), size_bytes=size,
                         complete=bool(cursor), next_cursor=None if cursor else VERSION + ":" + str(end), status=self.content_status)
            if self.binary or self.content_status != "available":
                value.update(status="unsupported" if self.binary else self.content_status, content="", bytes_read=0,
                    next_offset=offset, next_cursor=None, complete=False)
            if self.content_status == "missing":
                value.update(version=None, size_bytes=None, modified_at_ns=None)
        elif url.path.endswith("/artifacts"):
            value = sample("artifacts")
            cursor = query.get("cursor")
            value.update(cursor=cursor or "0", next_cursor=None if cursor else "1", complete=bool(cursor))
            value["items"][0].update(artifact_ref=ARTIFACT if cursor else "artifact-" + "c" * 40,
                relative_path="outputs/energy result.txt" if cursor else "first.txt")
        elif url.path.endswith("/logs"):
            value = sample("log")
            stream = query["stream"]
            content = "calculation failed" if stream == "stderr" else "step 1 finished"
            value.update(stream=stream, cursor=f"log-{stream}-0", content=content,
                next_cursor=f"log-{stream}-{len(content)}", available=True, complete=True, truncated=False)
        else:
            value = sample("detail")
            value["run"].update(run_ref=run, status=self.status, title="Energy calculation")
        value.update(workspace_key=workspace, run_ref=run)
        return 200, value


async def select(app, pilot, option):
    widget = app.query_one("#work-list", OptionList)
    widget.highlighted = widget.get_option_index(option)
    widget.focus()
    await pilot.press("enter")
    await settled(app, pilot)


async def open_second_file(app, pilot):
    app._command("next")
    await settled(app, pilot)
    files = app.query_one("#work-files", OptionList)
    files.focus()
    await pilot.press("enter")
    await settled(app, pilot)


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_default_work_to_output_keeps_each_server_workspace_and_reading_position(job_payload, tmp_path, language):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), language=language, refresh_seconds=999)
        async with app.run_test(size=(100, 32)) as pilot:
            await settled(app, pilot)
            assert len(app.home_items) == 3
            assert len(app.query(Input)) == 0
            assert set(app.home_items) == {"native:12345", "run:run-example-1", "run:run-second"}
            assert str(app.query_one("#work-primary", Button).label) == app.t("view_status")
            listing = app.query_one("#work-list", OptionList)
            listing.highlighted = listing.get_option_index("run:run-second")
            await pilot.pause(.05)
            assert str(app.query_one("#work-primary", Button).label) == app.t("results")
            for width in (40, 60, 100):
                await pilot.resize_terminal(width, 24)
                await pilot.pause(.05)
                app.save_screenshot(str(tmp_path / f"home-{language}-{width}.svg"))
                assert app.query_one("#work-list").region.height >= 10
            await select(app, pilot, "run:run-second")
            assert app.selected.workspace == "org:second" and app.mode == "files"
            await open_second_file(app, pilot)
            assert app.mode == "content" and app.result.values["content"] == "first output page"
            app._command("next")
            await settled(app, pilot)
            assert app.result.values["content"] == "second output page"
            cursor = app.cursor
            app._command("cost")
            await settled(app, pilot)
            assert app.result.values["status"] == "settled"
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "content" and app.cursor == cursor and app.result.values["content"] == "second output page"
            for width in (40, 60, 100):
                await pilot.resize_terminal(width, 24)
                await pilot.pause(.05)
                app.save_screenshot(str(tmp_path / f"result-{language}-{width}.svg"))
                assert app.query_one("#work-reading").region.height >= 10
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "files" and app.result.request_cursor == "1"
            assert app._highlight(app.query_one("#work-files", OptionList)) == ARTIFACT
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "home" and app._highlight(app.query_one("#work-list", OptionList)) == "run:run-second"

    with http_endpoint(fixture) as (origin, calls):
        asyncio.run(scenario(origin))
    assert all(call["method"] == "GET" for call in calls)
    assert not any("/workspaces" in call["path"] or "/runs/run-example-1" in call["path"] for call in calls)


@pytest.mark.parametrize("late_status", [200, 403, 401])
def test_return_while_content_is_pending_discards_late_data_and_errors(job_payload, late_status):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            app._command("next")
            await settled(app, pilot)
            fixture.block = True
            fixture.fail_content = late_status if late_status != 200 else 0
            try:
                app.query_one("#work-files", OptionList).focus()
                await pilot.press("enter")
                for _ in range(100):
                    if fixture.started.is_set():
                        break
                    await pilot.pause(.02)
                assert fixture.started.is_set()
                await pilot.press("escape")
                await pilot.press("escape")
                assert app.mode == "home" and app.selected is None
            finally:
                fixture.release.set()
            await settled(app, pilot)
            assert not app.auth_expired and not app._error and app.mode == "home"
            assert app.result is not None and app.artifact is None
            assert "first output page" not in str(app.query_one("#work-evidence", Static).content)

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


@pytest.mark.parametrize("status,code", [(401, "identity_expired"), (403, "run_file_read_denied"), (403, "run_read_denied")])
def test_current_permission_loss_clears_only_authorized_layers(job_payload, status, code):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-example-1")
            await open_second_file(app, pilot)
            fixture.fail_content, fixture.fail_code = status, code
            app.action_refresh()
            await settled(app, pilot)
            assert app.result is None and app.artifact is None and not app.positions and app._web_url is None
            assert "first output page" not in str(app.query_one("#work-evidence", Static).content)
            if code == "run_file_read_denied":
                assert app.detail is not None and app.selected is not None and app.mode == "content"
            else:
                assert app.detail is None and app.selected is None and not app.home_items and app.mode == "home"
            assert app.auth_expired == (status == 401)

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


@pytest.mark.parametrize("status,expected", [("failed", "stderr"), ("running", "run")])
def test_work_state_selects_relevant_evidence_without_technical_setup(job_payload, status, expected):
    fixture = ResearchHTTP(job_payload)
    fixture.status = status

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            listing = app.query_one("#work-list", OptionList)
            listing.highlighted = listing.get_option_index("run:run-example-1")
            await pilot.pause(.05)
            assert str(app.query_one("#work-primary", Button).label) == app.t("logs" if status == "failed" else "view_status")
            await select(app, pilot, "run:run-example-1")
            assert app.mode == expected and len(app.query(Input)) == 0
            if status == "failed":
                assert app.result.values["content"] == "calculation failed"
            else:
                assert "PD" not in str(app.query_one("#work-evidence", Static).content)

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


def test_empty_and_unavailable_history_are_distinct_and_never_fake_zero_work(job_payload):
    fixture = ResearchHTTP(job_payload)
    fixture.empty = True

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            assert app.t("empty") in str(app.query_one("#work-evidence", Static).content)
            fixture.fail_history = 503
            app.action_refresh()
            await settled(app, pilot)
            body = str(app.query_one("#work-evidence", Static).content)
            assert app.t("recent_failed") in body and app.t("empty") not in body

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


def test_binary_result_saves_through_existing_grant_and_keeps_identity_at_center(job_payload, tmp_path):
    fixture = ResearchHTTP(job_payload)
    fixture.binary = True
    data = b"binary\0result\xff"
    fixture.download_size = len(data)
    destination = tmp_path / "research result.bin"

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            await open_second_file(app, pilot)
            assert app.result.values["status"] == "unsupported" and app._can_save()
            await pilot.click("#work-primary")
            await pilot.pause(.05)
            app.screen.query_one(Input).value = str(destination)
            await pilot.press("enter")
            for _ in range(200):
                await pilot.pause(.02)
                if app._save_screen is None:
                    break
            assert app._save_screen is None and destination.read_bytes() == data
            assert app.mode == "content" and app.selected.workspace == "org:second"
            assert str(destination) in str(app.query_one("#work-status", Static).content)

    with binary_endpoint(lambda call, _: response(data, call)) as (site, reads):
        fixture.site = site
        with http_endpoint(fixture) as (origin, calls):
            asyncio.run(scenario(origin))
    assert all(call["bearer"] is None and call["capability"] == "synthetic-file-capability" for call in reads)
    issued = [call for call in calls if call["method"] == "POST"]
    assert len(issued) == 1 and issued[0]["body"]["artifact_cursor"] == "1"
    assert not list(tmp_path.glob(".sai-download-*"))


def test_history_pagination_survives_work_inspection_and_returns_to_previous_page(job_payload):
    fixture = ResearchHTTP(job_payload)
    fixture.history_pages = True

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            app._command("next")
            await settled(app, pilot)
            assert "run:run-third" in app.home_items and "run:run-second" not in app.home_items
            await select(app, pilot, "run:run-third")
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.home_cursor == "run-second" and "run:run-third" in app.home_items
            app._command("previous")
            await settled(app, pilot)
            assert app.home_cursor is None and "run:run-second" in app.home_items

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


@pytest.mark.parametrize("selector", ["native", "workspace"])
def test_explicit_cli_scope_is_preserved_without_broad_history_fallback(job_payload, selector):
    fixture = ResearchHTTP(job_payload)
    fixture.scope = "org_account"
    query = JobQuery(site_id="site-a", scope="org-account", **({"account_name": "org-example"} if selector == "native"
        else {"workspace_key": "org:second"}))

    async def scenario(origin):
        app = Workbench(client(origin), query, refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert app.job_query == query
            assert ("run:run-second" in app.home_items) == (selector == "workspace")
            if selector == "native":
                assert app.result["recent"] is None
                app._command("workspaces")
                await settled(app, pilot)
                app.query_one("#work-choices", OptionList).focus()
                await pilot.press("enter")
                await settled(app, pilot)
                assert app.job_query.workspace_key == "org:second" and app.job_query.account_name is None
                assert "run:run-second" in app.home_items

    with http_endpoint(fixture) as (origin, calls):
        asyncio.run(scenario(origin))
    assert not any("my-runs" in call["path"] for call in calls)


def test_independent_storage_denial_and_secondary_navigation_preserve_current_result(job_payload):
    fixture = ResearchHTTP(job_payload)
    fixture.storage_denied = True

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            app._command("stdout")
            await settled(app, pilot)
            app._command("cost")
            await settled(app, pilot)
            app._command("files")
            await settled(app, pilot)
            await open_second_file(app, pilot)
            app._command("cost")
            await settled(app, pilot)
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "content"
            app._command("storage_choices")
            await settled(app, pilot)
            app.query_one("#work-choices", OptionList).focus()
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.mode == "storage" and app._error and app.selected.reference == "run-second"
            await pilot.press("escape")
            await settled(app, pilot)
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "content" and app.result.values["content"] == "first output page"

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


def test_empty_work_opens_native_pilot_and_keeps_resource_choice_optional(job_payload):
    fixture = ResearchHTTP(job_payload)
    fixture.empty = True

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await pilot.click("#work-primary")
            await settled(app, pilot)
            assert app.mode == "home"
            assert opened == [origin + "/v1/account/pilot/entry?site_id=site-a"]
            assert len(calls) == 2
            app._command("catalog")
            await settled(app, pilot)
            assert app.mode == "catalog" and len(app.query(Input)) == 0
            app.query_one("#work-choices", OptionList).focus()
            await pilot.press("enter")
            await pilot.pause(.05)
            assert app.mode == "resource"
            await pilot.click("#work-primary")
            assert len(opened) == 2 and "site_id=site-a" in opened[-1] and "partition_ref=" in opened[-1]
            assert "prepare" in opened[-1] and "workspace" not in opened[-1]

    with http_endpoint(fixture) as (origin, calls):
        asyncio.run(scenario(origin))
    assert all(call["method"] == "GET" for call in calls)


def test_cancel_binary_save_waits_for_transfer_and_removes_partial_file(job_payload, tmp_path):
    fixture = ResearchHTTP(job_payload)
    fixture.binary = True
    data = b"x" * (RANGE_BYTES + 17)
    fixture.download_size = len(data)
    destination = tmp_path / "canceled.bin"
    started, release = threading.Event(), threading.Event()

    def binary_reply(call, count):
        if count == 2:
            started.set()
            assert release.wait(6)
        return response(data, call)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            await open_second_file(app, pilot)
            app.action_save()
            await pilot.pause(.05)
            app.screen.query_one(Input).value = str(destination)
            await pilot.press("enter")
            try:
                for _ in range(150):
                    if started.is_set():
                        break
                    await pilot.pause(.02)
                assert started.is_set()
                await pilot.press("escape")
                assert app._save_screen is not None and not destination.exists()
            finally:
                release.set()
            for _ in range(150):
                if app._save_screen is None:
                    break
                await pilot.pause(.02)
            assert app._save_screen is None and not destination.exists()
            assert app.t("save_cancelled") in str(app.query_one("#work-status", Static).content)

    with binary_endpoint(binary_reply) as (site, _):
        fixture.site = site
        with http_endpoint(fixture) as (origin, _):
            asyncio.run(scenario(origin))
    assert not list(tmp_path.glob(".sai-download-*"))


def test_native_activity_never_acquires_managed_files_from_a_matching_job_number(job_payload):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "native:12345")
            assert app.mode == "native" and app.selected.workspace is None
            assert not {"files", "stdout", "stderr", "save"}.intersection(app._commands())
            assert app.t("native_hint") in str(app.query_one("#work-evidence", Static).content)

    with http_endpoint(fixture) as (origin, calls):
        asyncio.run(scenario(origin))
    assert not any("/compute/cli/runs/" in call["path"] for call in calls)


def test_visible_context_menu_runs_actions_and_refresh_preserves_keyboard_focus(job_payload):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            listing = app.query_one("#work-list", OptionList)
            listing.highlighted = listing.get_option_index("run:run-second")
            button = app.query_one("#work-more", Button)
            button.focus()
            app.action_refresh()
            await settled(app, pilot)
            assert app.focused is button and app._highlight(listing) == "run:run-second"
            await select(app, pilot, "run:run-second")
            await pilot.click("#work-more")
            await pilot.pause(.05)
            options = app.screen.query_one(OptionList)
            options.highlighted = options.get_option_index("cost")
            options.focus()
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.mode == "cost" and app.result.values["status"] == "settled"

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


@pytest.mark.parametrize("status", ["changed", "missing"])
def test_changed_or_missing_result_cannot_restore_old_content_or_save(job_payload, status):
    fixture = ResearchHTTP(job_payload)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            await open_second_file(app, pilot)
            fixture.content_status = status
            app.action_refresh()
            await settled(app, pilot)
            assert app.artifact is None and not app._can_save() and "content" not in app.positions
            assert "first output page" not in str(app.query_one("#work-evidence", Static).content)
            app.action_refresh()
            await settled(app, pilot)
            assert app.mode == "files" and app.result.request_cursor == "1"

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))


def test_cold_entry_offers_explicit_login_and_cancel_then_returns_to_real_work_reads(job_payload):
    fixture = ResearchHTTP(job_payload)

    class Provider:
        clock = staticmethod(time.time)
        pending = None
        started = 0
        signed_in = approved = False

        def get(self):
            if not self.signed_in:
                raise AuthenticationError("No device session", code="credentials_unavailable")
            return TokenLease("fixture-token", None, "environment")

        def start_device_authorization(self):
            self.started += 1
            self.pending = "device-" + str(self.started), int(self.clock()) + 60
            return DeviceAuthorization(self.pending[0], "ABCD-EFGH", "https://identity.example.org/activate", self.pending[1], 1)

        def poll_device_token(self, *, device_code):
            assert self.pending[0] == device_code
            return DeviceTokenResult("fixture-token", int(self.clock()) + 300, "fixture-refresh", None) if self.approved else None

        def pending_device_code(self):
            return self.pending

        def clear_pending_device_code(self, *, device_code=None):
            if device_code is None or self.pending is not None and self.pending[0] == device_code:
                self.pending = None

        def install_device_tokens(self, result):
            self.signed_in = True

    async def scenario(origin, calls):
        provider = Provider()
        reader = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=3), token_provider=provider)
        app = Workbench(reader, JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert app.auth_expired and not calls and provider.started == 0
            assert str(app.query_one("#work-primary", Button).label) == app.t("login")
            await pilot.click("#work-primary")
            for _ in range(100):
                await pilot.pause(.02)
                if app._login_screen and app._login_screen.authorization:
                    break
            assert app._login_screen is not None and provider.started == 1
            assert not app._commands() and not calls and len(app.query(Input)) == 0
            app.action_refresh()
            await pilot.press("escape")
            for _ in range(100):
                await pilot.pause(.02)
                if app._login_screen is None:
                    break
            assert app.auth_expired and provider.pending is None and not provider.signed_in
            provider.approved = True
            await pilot.click("#work-primary")
            for _ in range(100):
                await pilot.pause(.02)
                if provider.signed_in and app._login_screen is None:
                    break
            await settled(app, pilot)
            assert not app.auth_expired and len(app.home_items) == 3 and provider.started == 2
            assert provider.pending is None and app.mode == "home"

    with http_endpoint(fixture) as (origin, calls):
        asyncio.run(scenario(origin, calls))
    assert len(calls) == 2 and all(call["method"] == "GET" for call in calls)
