import asyncio
import builtins
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
from threading import Event, current_thread
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.auth import TokenLease
from sai_cli import config as config_module
from sai_cli import cli as cli_module
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


@pytest.mark.parametrize("output_format", ["json", "table"])
def test_status_uses_self_authorized_central_http_without_site_grant(tmp_path, monkeypatch, output_format):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(cli_module, "_load_overview_console", lambda: pytest.fail("batch status must not load UI"))
    def reply(call, _):
        parsed = urlsplit(call["path"])
        assert parsed.path == "/v1/account/cli/overview"
        assert parse_qs(parsed.query) == {"site_id": ["site-a"], "slurm_account_name": ["org-example"]}
        return 200, sample()
    with http_endpoint(reply) as (origin, calls):
        for args in (["--site", "site-a", "status"], ["status", "--site", "site-a"]):
            out, err = StringIO(), StringIO()
            rc = main([*args, "--account", "org-example", "--format", output_format, "--base-url", origin],
                      environ={"SAI_TOKEN": "test-bearer", "XDG_CONFIG_HOME": str(tmp_path)}, stdout=out, stderr=err)
            assert rc == 0 and not err.getvalue()
            if output_format == "json":
                assert json.loads(out.getvalue())["inbox"]["unread_count"] == 4
            else:
                assert "未读消息  4 条" in out.getvalue()
    assert len(calls) == 2 and all(call["method"] == "GET" for call in calls)


@pytest.mark.parametrize("managed,explicit,expected", [
    (True, None, "org-applied"),
    (True, "org-example", "org-example"),
    (False, None, None),
])
def test_status_retains_managed_login_account_and_explicit_override(tmp_path, monkeypatch, managed, explicit, expected):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    def reply(call, _):
        query = parse_qs(urlsplit(call["path"]).query)
        assert query == {"site_id": ["site-a"], **({"slurm_account_name": [expected]} if expected else {})}
        value = sample()
        value["context"]["slurm_account"] = expected or "org-example"
        return 200, value
    with http_endpoint(reply) as (origin, calls):
        config = tmp_path / "managed.toml"
        config.write_text(f'[profiles.default]\nbase_url = "{origin}"\nsite_id = "site-a"\nrequire_site_capability = true\n')
        config.chmod(0o644)
        monkeypatch.setattr(config_module, "_MANAGED_CONFIG_PATH", config)
        monkeypatch.setattr(config_module, "_MANAGED_CONFIG_OWNER_UID", os.getuid())
        args = ["status", *(["--account", explicit] if explicit else [])]
        out, err = StringIO(), StringIO()
        rc = main(args, environ={"SAI_TOKEN": "test-bearer", "SAI_CONFIG": str(config),
                  "SAI_MANAGED_LOGIN_NODE": "1" if managed else "0", "_SAI_LOGIN_ACCOUNT": "org-applied"},
                  stdout=out, stderr=err)
        assert rc == 0 and not err.getvalue(), err.getvalue()
        assert json.loads(out.getvalue())["context"]["slurm_account"] == (expected or "org-example")
    assert len(calls) == 1


@pytest.mark.parametrize("http_status,missing_rich,expected_exit", [
    (200, False, 0), (403, False, 4), (200, True, 2), (403, True, 4),
])
def test_panel_overlaps_import_with_http_and_joins_before_return(tmp_path, monkeypatch, http_status, missing_rich, expected_exit):
    pytest.importorskip("rich")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    import_started, response_ready = Event(), Event()
    workers = []
    caller = current_thread()
    original_load = cli_module._load_overview_console
    original_read = PortalClient.account_overview
    original_import = builtins.__import__

    def load_console():
        workers.append(current_thread())
        import_started.set()
        assert response_ready.wait(2)
        return original_load()

    def read(client, *args, **kwargs):
        assert current_thread() is caller
        return original_read(client, *args, **kwargs)

    def import_module(name, *args, **kwargs):
        if missing_rich and name == "rich.console":
            raise ModuleNotFoundError("No module named 'rich'", name="rich")
        return original_import(name, *args, **kwargs)

    def reply(call, _):
        assert import_started.wait(2)
        response_ready.set()
        return http_status, sample() if http_status == 200 else {"detail": "scope unavailable"}

    monkeypatch.setattr(cli_module, "_load_overview_console", load_console)
    monkeypatch.setattr(PortalClient, "account_overview", read)
    monkeypatch.setattr(builtins, "__import__", import_module)
    with http_endpoint(reply) as (origin, calls):
        out, err = StringIO(), StringIO()
        rc = main(["status", "--format", "tui", "--site", "site-a", "--base-url", origin],
                  environ={"SAI_TOKEN": "test-bearer", "XDG_CONFIG_HOME": str(tmp_path)}, stdout=out, stderr=err)
    assert rc == expected_exit and len(calls) == 1
    assert len(workers) == 1 and workers[0] is not caller and not workers[0].is_alive()
    assert bool(out.getvalue()) is (expected_exit == 0)
    assert bool(err.getvalue()) is (expected_exit != 0)
    if expected_exit == 2:
        assert "install sai-cli[tui]" in err.getvalue()


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
        assert parse_qs(urlsplit(call["path"]).query) == {"site_id": ["site-a"], "slurm_account_name": ["org-example"]}
        return (403, {"detail": "scope unavailable"}) if denied else (200, sample())
    async def scenario(client):
        app = Workbench(client, JobQuery(site_id="site-a", scope="org-account", account_name="org-jobs"),
                        overview_account="org-example", storage_workspace_key="org:storage",
                        initial_view="overview", refresh_seconds=999)
        opened = []
        app.open_url = opened.append
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            assert "overview" in app.results and not app.query_one("#job-scope-controls").display
            assert app.job_query.account_name == "org-jobs" and app.storage_workspace_key == "org:storage"
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
