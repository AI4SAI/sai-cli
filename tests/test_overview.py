import asyncio
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.auth import TokenLease
from sai_cli.cli import main
from sai_cli.client import JobQuery, PortalClient
from sai_cli.errors import ContractError
from sai_cli.overview import AccountOverview
from sai_cli.overview_view import render_overview
from sai_cli.transport import JsonTransport
from test_site_transport import http_endpoint


SAMPLE = Path(__file__).resolve().parents[1] / "contracts/account-overview/v1/sample.json"


def sample():
    return json.loads(SAMPLE.read_text())


def test_overview_keeps_money_scope_and_sensitive_field_allowlist():
    value = sample()
    value["token"] = "private-token"
    value["funds"]["ledger"] = ["private-ledger"]
    value["inbox"]["items"][0]["payload"] = {"secret": "private-payload"}
    parsed = AccountOverview.from_payload(value, site_id="site-a", account="org-example", request_id="test")
    assert "private-" not in json.dumps(parsed.as_dict())
    assert parsed.values["funds"]["net_balance"] == "1280.50000000"
    text = render_overview(parsed, work_dir="/org/org-example/run")
    assert "¥1,280.50" in text and "20,000 点" in text and "4 条" in text
    assert parsed.messages_url("https://portal.example.org") == "https://portal.example.org/portal/#/portal/workspaces/org%3Aexample/site-a/messages"
    for changed in ("other-site",):
        with pytest.raises(ContractError):
            AccountOverview.from_payload(value, site_id=changed, request_id="test")
    with pytest.raises(ContractError):
        AccountOverview.from_payload(value, site_id="site-a", account="org-other", request_id="test")


@pytest.mark.parametrize("field,bad", [("net_balance", "1e99999999"), ("available_credit", "NaN"),
                                        ("net_balance", True), ("postpaid_available", "infinity")])
def test_overview_rejects_unsafe_amounts(field, bad):
    value = sample()
    value["funds"][field] = bad
    with pytest.raises(ContractError):
        AccountOverview.from_payload(value, site_id="site-a", request_id="test")


def test_overview_failure_and_message_states_are_not_fabricated():
    value = sample()
    value["inbox"]["items"][0]["title"] = "unsafe\x1b[31m"
    with pytest.raises(ContractError):
        AccountOverview.from_payload(value, site_id="site-a", request_id="test")

    value = sample()
    value["funds"]["state"] = "not_authorized"
    with pytest.raises(ContractError):
        AccountOverview.from_payload(value, site_id="site-a", request_id="test")
    for key in value["funds"]:
        if key not in {"state", "currency"}:
            value["funds"][key] = None
    parsed = AccountOverview.from_payload(value, site_id="site-a", request_id="test")
    text = render_overview(parsed)
    assert "未授权资金读取" in text and "¥0" not in text
    value["inbox"]["unread_count"] = 0
    with pytest.raises(ContractError):
        AccountOverview.from_payload(value, site_id="site-a", request_id="test")


def test_missing_default_does_not_hide_personal_verification_action():
    value = sample()
    value["context"] = {key: "unavailable" if key == "state" else None for key in value["context"]}
    value["funds"] = value["inbox"] = None
    value["access"].update(verification_current=False, initial_verification_deadline="2026-10-01T00:00:00Z")
    text = render_overview(AccountOverview.from_payload(value, site_id="site-a", request_id="test"))
    assert "默认身份" in text and "认证截止" in text and "完成认证" in text
    assert "¥0" not in text


def test_status_uses_self_authorized_central_http_without_site_grant(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    def reply(call, _):
        parsed = urlsplit(call["path"])
        assert parsed.path == "/v1/account/cli/overview"
        assert parse_qs(parsed.query) == {"site_id": ["site-a"], "slurm_account_name": ["org-example"]}
        return 200, sample()
    with http_endpoint(reply) as (origin, calls):
        for args in (["--site", "site-a", "status"], ["status", "--site", "site-a"]):
            out, err = StringIO(), StringIO()
            rc = main([*args, "--account", "org-example", "--base-url", origin],
                      environ={"SAI_TOKEN": "test-bearer", "XDG_CONFIG_HOME": str(tmp_path)}, stdout=out, stderr=err)
            assert rc == 0 and not err.getvalue()
            assert json.loads(out.getvalue())["inbox"]["unread_count"] == 4
    assert len(calls) == 2 and all(call["method"] == "GET" for call in calls)


@pytest.mark.parametrize("width", [40, 80, 120])
def test_terminal_panel_fits_width_and_treats_markup_as_text(width):
    pytest.importorskip("rich")
    from rich.console import Console
    from rich.cells import cell_len
    from sai_cli.overview_view import overview_panel
    value = sample()
    value["inbox"]["items"][0]["title"] = "[red]这是普通文字，不是颜色标记[/red]"
    parsed = AccountOverview.from_payload(value, site_id="site-a", request_id="test")
    out = StringIO()
    Console(file=out, width=width, color_system=None).print(overview_panel(parsed, work_dir="/org/org-example/很长的目录/run 1"))
    rendered = out.getvalue()
    assert all(cell_len(line) <= width for line in rendered.splitlines())
    assert "[red]" in rendered and "\x1b" not in rendered
    assert "SAI" in rendered and "未读消息" in rendered
    value["inbox"]["items"][0]["title"] = "很长的通知标题" * 20
    parsed = AccountOverview.from_payload(value, site_id="site-a", request_id="test")
    out = StringIO()
    Console(file=out, width=width, color_system=None).print(overview_panel(parsed))
    assert len(out.getvalue().splitlines()) <= 16


def test_interactive_overview_refresh_navigation_and_revocation(tmp_path, monkeypatch):
    pytest.importorskip("textual")
    from textual.widgets import Button, Static
    from sai_cli.tui import Workbench
    from test_tui import settled
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    denied = False
    def reply(call, _):
        return (403, {"detail": "scope unavailable"}) if denied else (200, sample())
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a"), initial_view="overview", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            assert "overview" in app.results and not app.query_one("#job-scope-controls").display
            await pilot.click("#overview-messages")
            assert opened == [app.results["overview"].messages_url(client.transport.base_url)]
            nonlocal denied
            denied = True
            await pilot.press("f5")
            await settled(app, pilot)
            assert "overview" not in app.results
            assert app.query_one("#overview-messages", Button).disabled
            assert str(app.query_one("#overview-summary", Static).render()) == ""
    with http_endpoint(reply) as (origin, calls):
        provider = SimpleNamespace(get=lambda: TokenLease("test-session", None, "environment"))
        asyncio.run(scenario(PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2), token_provider=provider)))
