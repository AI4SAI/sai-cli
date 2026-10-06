"""Tools stay inside the user's work; they do not become separate home pages."""
import asyncio
from io import StringIO
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, OptionList, Static

from sai_cli.client import JobQuery
from sai_cli.workbench import Workbench
from test_overview import sample as overview_sample
from test_resource_preparation import document
from test_site_transport import http_endpoint
from test_workbench_flow import ResearchHTTP, client, select, settled


@pytest.mark.parametrize("width", [40, 60, 100])
def test_compare_choices_and_prepare_preserve_the_selected_resource(job_payload, width):
    base = ResearchHTTP(job_payload)

    def reply(call, count):
        if urlsplit(call["path"]).path.endswith("resource-catalog"):
            return 200, document()
        return base(call, count)

    async def scenario(origin, calls):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(width, 24)) as pilot:
            await settled(app, pilot)
            app._command("catalog")
            await settled(app, pilot)
            choices = app.query_one("#work-choices", OptionList)
            choices.focus()
            await pilot.press("enter")
            app._command("compare")
            count = len(calls)
            await pilot.press("escape", "down", "enter")
            app._command("compare")
            await pilot.pause(.05)
            assert app.compared == ["gpu-standard", "cpu-standard"]
            assert app.result[1]["name"] == "cpu-standard"
            assert len(calls) == count
            output = StringIO()
            Console(file=output, width=width, color_system=None).print(app.query_one("#work-evidence", Static).content)
            for text in ("科研GPU候选[literal]", "CPU独立候选", "normal"):
                assert text in "".join(output.getvalue().split())
            app.action_primary()
            assert parse_qs(urlsplit(opened[-1]).fragment.split("?", 1)[1]) == {
                "site_id": ["site-a"], "partition_ref": ["cpu-standard"]}
            assert len(calls) == count
            app.action_refresh()
            assert app.compared == [] and app._web_url is None
            await settled(app, pilot)
            assert app.mode == "catalog"

    with http_endpoint(reply) as (origin, calls):
        asyncio.run(scenario(origin, calls))


def test_account_messages_are_explicit_and_revocation_preserves_work(job_payload):
    base = ResearchHTTP(job_payload)
    denied = False

    def reply(call, count):
        url = urlsplit(call["path"])
        if url.path.endswith("/overview"):
            assert parse_qs(url.query) == {"site_id": ["site-a"], "slurm_account_name": ["org-example"]}
            return (403, {"detail": "scope unavailable"}) if denied else (200, overview_sample())
        return base(call, count)

    async def scenario(origin):
        nonlocal denied
        app = Workbench(client(origin), JobQuery(site_id="site-a"), overview_account="org-example", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            await select(app, pilot, "run:run-second")
            app._command("overview")
            await settled(app, pilot)
            assert opened == []
            expected = app.result.messages_url(origin)
            app.action_primary()
            assert opened == [expected]
            denied = True
            app.action_refresh()
            await settled(app, pilot)
            assert app.result is None and app._web_url is None
            assert str(app.query_one("#work-evidence", Static).content) == ""
            assert app.selected.reference == "run-second"
            await pilot.press("escape")
            await settled(app, pilot)
            assert app.mode == "files" and app.selected.workspace == "org:second"

    with http_endpoint(reply) as (origin, _):
        asyncio.run(scenario(origin))


def test_next_and_previous_pages_are_visible_choices(job_payload):
    fixture = ResearchHTTP(job_payload)
    fixture.history_pages = True

    async def activate(app, pilot, selector, identifier):
        widget = app.query_one(selector, OptionList)
        widget.highlighted = widget.get_option_index(identifier)
        widget.focus()
        await pilot.pause(.05)
        assert not app.query_one("#work-primary", Button).disabled
        await pilot.press("enter")
        await settled(app, pilot)

    async def scenario(origin):
        app = Workbench(client(origin), JobQuery(site_id="site-a"), refresh_seconds=999)
        async with app.run_test(size=(40, 24)) as pilot:
            await settled(app, pilot)
            await activate(app, pilot, "#work-list", "nav:next")
            assert "run:run-third" in app.home_items
            await activate(app, pilot, "#work-list", "nav:previous")
            assert "run:run-second" in app.home_items
            await select(app, pilot, "run:run-second")
            await activate(app, pilot, "#work-files", "nav:next")
            assert app.result.request_cursor == "1"
            await activate(app, pilot, "#work-files", "nav:previous")
            assert app.result.request_cursor is None

    with http_endpoint(fixture) as (origin, _):
        asyncio.run(scenario(origin))
