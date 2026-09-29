import asyncio
from copy import deepcopy
from io import StringIO
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.catalog import ResourceCatalog
from sai_cli.errors import ConfigError


def document():
    from test_tui import catalog
    data = catalog()
    data["compute"][0].update(
        title="科研 GPU 候选 [literal]", summary="完整用途说明：训练与科学模拟。" * 12,
        scenarios=["模型训练", "分子动力学"],
    )
    data["compute"][1].update(title="CPU 独立候选", summary="用于并行数据处理。", scenarios=["数据处理"])
    return data


def parsed(data=None):
    return ResourceCatalog.from_payload(document() if data is None else data, site_id="site-a", request_id="catalog")


def test_preparation_url_only_uses_current_site_and_one_exact_compute_candidate():
    url = urlsplit(parsed().preparation_url("https://console.example/prefix?ignored=1#old", "gpu-standard"))
    assert (url.scheme, url.netloc, url.path, url.query) == ("https", "console.example", "/portal/", "")
    route, query = url.fragment.split("?", 1)
    assert route == "/portal/resources/prepare"
    assert parse_qs(query) == {"site_id": ["site-a"], "partition_ref": ["gpu-standard"]}
    for reference in (None, "absent", "Project storage", "x" * 65, "gpu/standard", "gpu\nstandard"):
        with pytest.raises(ConfigError): parsed().preparation_url("https://console.example", reference)
    duplicate = document()
    duplicate["compute"].append(deepcopy(duplicate["compute"][0]))
    with pytest.raises(ConfigError): parsed(duplicate).preparation_url("https://console.example", "gpu-standard")
    wider = document()
    wider["compute"][0]["name"] = "x" * 65
    with pytest.raises(ConfigError): parsed(wider).preparation_url("https://console.example", "x" * 65)


pytest.importorskip("textual")
from rich.console import Console
from textual.widgets import Button, DataTable, Input, Static, TabbedContent
from sai_cli.auth import TokenLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.transport import JsonTransport
from sai_cli.tui import Workbench
from sai_cli.tui_views import resource_panel
from test_site_transport import http_endpoint
from test_tui import settled


def detail(app, width=100):
    output = StringIO()
    Console(file=output, width=width, color_system=None).print(app.query_one("#details", Static).content)
    return output.getvalue()


@pytest.mark.parametrize("width", [40, 60, 100])
@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_resource_candidate_comparison_and_prepare_are_separate_without_job_history(tmp_path, monkeypatch, width, language):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    def reply(call, _):
        assert call["method"] == "GET" and call["path"] == "/v1/account/sites/site-a/resource-catalog"
        assert call["capability"] is None
        return 200, document()
    async def scenario(client, calls):
        app = Workbench(client, JobQuery(site_id="site-a", scope="org-account", account_name="irrelevant-account", states=("R",)),
                        initial_view="resources", language=language, refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(width, 24)) as pilot:
            await settled(app, pilot)
            assert not app.query_one("#job-scope-controls").display and not app.query_one("#job-filter-controls").display
            context = str(app.query_one("#context", Static).render())
            assert "irrelevant-account" not in context and app.t("catalog_context") in context
            assert app.selected_resource is None and app.compared == [] and len(calls) == 1
            assert app.query_one("#prepare-resource", Button).disabled
            table = app.query_one("#resources-table", DataTable)
            table.focus()
            await pilot.press("enter", "c", "down", "enter", "c")
            await pilot.pause(.05)
            assert app.selected_resource == "cpu-standard" and app.compared == ["gpu-standard", "cpu-standard"]
            await pilot.press("up", "enter")
            await pilot.pause(.05)
            assert app.selected_resource == "gpu-standard" and app.compared[-1] == "cpu-standard"
            for identifier in ("compare-resource", "clear-comparison", "use-partition", "prepare-resource"):
                button = app.query_one("#" + identifier, Button)
                assert 0 <= button.region.x < button.region.right <= width
            rendered = detail(app, width)
            assert "科研 GPU 候选 [literal]".replace(" ", "") in "".join(rendered.split())
            for expected in ("完整用途说明", "分子动力学", "CPU", "QOS"):
                assert expected in rendered
            assert app.t("resource_meaning").replace(" ", "") in "".join(rendered.split())
            app._tick();await pilot.pause(.03)
            assert len(calls) == 1
            await pilot.press("w")
            assert len(calls) == 1 and app.clipboard == ""
            url=urlsplit(opened[-1])
            assert url.netloc == urlsplit(client.transport.base_url).netloc
            assert parse_qs(url.fragment.split("?",1)[1]) == {"site_id":["site-a"],"partition_ref":["gpu-standard"]}
            assert "irrelevant" not in opened[-1] and "workspace" not in opened[-1]
            app.action_copy_web_link();assert app.clipboard==opened[-1]
            table.focus();await pilot.press("down","down","enter");await pilot.pause(.05)
            assert app.selected_resource is None and app._web_url is None
            assert app.query_one("#prepare-resource",Button).disabled and app.query_one("#compare-resource",Button).disabled
            assert "Project storage" in detail(app)
            await pilot.resize_terminal(width,24);assert "Project storage" in detail(app)
            assert app.compared == ["gpu-standard","cpu-standard"]
            table.focus();await pilot.press("home","enter");await pilot.pause(.05)
            app.save_screenshot(str(tmp_path/f"resources-{width}-{language}.svg"))
    with http_endpoint(reply) as (origin,calls):
        client=PortalClient(transport=JsonTransport(base_url=origin,timeout_seconds=3),
                            token_provider=SimpleNamespace(get=lambda:TokenLease("test-token",None,"environment")))
        asyncio.run(scenario(client,calls))


@pytest.mark.parametrize("width", [40, 60, 100])
def test_comparison_columns_reflow_instead_of_truncating_facts(width):
    data=document();output=StringIO()
    Console(file=output,width=width,color_system=None).print(resource_panel(None,data["compute"],"en-US",width))
    rendered=output.getvalue()
    assert "科研 GPU 候选 [literal]".replace(" ","") in "".join(rendered.split())
    assert "CPU 独立候选".replace(" ","") in "".join(rendered.split())
    assert "Unknown" in rendered and "QOS" in rendered and "normal" in rendered


@pytest.mark.parametrize("transition", ["refresh", "error", "tab", "stale"])
def test_resource_candidate_and_link_clear_before_catalog_or_context_change(monkeypatch, transition):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    started,release=threading.Event(),threading.Event();block=False;deny=False
    def reply(call,_):
        if block:
            started.set();assert release.wait(5)
        return (503,{"private":"hidden"}) if deny else (200,document())
    async def scenario(client):
        nonlocal block,deny
        app=Workbench(client,JobQuery(site_id="site-a"),refresh_seconds=999)
        opened=[];app.open_url=opened.append
        async with app.run_test(size=(60,24)) as pilot:
            await settled(app,pilot);table=app.query_one("#resources-table",DataTable);table.focus()
            await pilot.press("enter","w");await pilot.pause(.05)
            assert app.selected_resource=="gpu-standard" and app._web_url is not None
            if transition=="tab":
                app.query_one("#views",TabbedContent).active="storage";await pilot.pause(.05)
            else:
                deny=transition=="error";block=transition=="stale"
                app.action_refresh()
            assert app.selected_resource is None and app._web_url is None
            if block:
                try:
                    for _ in range(80):
                        if started.is_set():break
                        await pilot.pause(.02)
                    assert started.is_set()
                    app.query_one("#views",TabbedContent).active="storage";await pilot.pause(.05)
                finally:release.set()
            await settled(app,pilot)
            app.action_open_web()
            assert len(opened)==1 and app.selected_resource is None and app._web_url is None
            if transition=="error":assert app.catalog is None
    with http_endpoint(reply) as (origin,_):
        client=PortalClient(transport=JsonTransport(base_url=origin,timeout_seconds=3),
                            token_provider=SimpleNamespace(get=lambda:TokenLease("test-token",None,"environment")))
        asyncio.run(scenario(client))


def test_candidate_is_not_replaced_when_two_comparison_slots_are_full():
    data = document()
    data["compute"].append({**deepcopy(data["compute"][0]), "name": "third-partition", "title": "Third candidate"})
    class Client:
        transport = SimpleNamespace(base_url="https://console.example")
        def resource_catalog(self, site): return parsed(data)
    async def scenario():
        app=Workbench(Client(),JobQuery(site_id="site-a"),refresh_seconds=999)
        async with app.run_test(size=(60,24)) as pilot:
            await settled(app,pilot);app.query_one("#resources-table",DataTable).focus()
            await pilot.press("enter","c","down","enter","c","down","enter","c")
            assert app.selected_resource == "third-partition"
            assert app.compared == ["gpu-standard","cpu-standard"]
            assert "remove one first" in str(app.query_one("#status",Static).render())
            assert parse_qs(urlsplit(app._resource_preparation_url()).fragment.split("?",1)[1])["partition_ref"] == ["third-partition"]
    asyncio.run(scenario())
