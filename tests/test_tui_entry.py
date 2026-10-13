"""One-shot summaries stay separate from the interactive terminal entry."""
from io import StringIO
import builtins
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import build_parser, main
from sai_cli import cli as cli_module
from test_overview import sample
from test_site_transport import http_endpoint


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("language,label", [("zh-CN", "组织共享"), ("en-US", "Shared")])
def test_formatted_status_reads_one_summary_and_returns_without_input(tmp_path, monkeypatch, prefix, language, label):
    pytest.importorskip("rich")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(builtins, "input", lambda *a: pytest.fail("summary must not prompt"))
    def reply(call, _):
        parsed = urlsplit(call["path"])
        assert parsed.path == "/v1/account/cli/overview"
        assert parse_qs(parsed.query) == {"site_id": ["site-a"]}
        return 200, sample()
    with http_endpoint(reply) as (origin, calls):
        options = ["--site", "site-a", "--base-url", origin]
        command = ["status", "--format", "tui", "--language", language]
        out, err = StringIO(), StringIO()
        rc = main(options + command if prefix else command + options,
                  environ={"SAI_TOKEN": "test-bearer", "XDG_CONFIG_HOME": str(tmp_path)},
                  stdout=out, stderr=err)
    assert rc == 0 and not err.getvalue(), err.getvalue()
    assert len(calls) == 1 and calls[0]["method"] == "GET"
    assert label in out.getvalue() and "1,280.50" in out.getvalue()
    assert "20,000" in out.getvalue() and "sai tui" not in out.getvalue()
    assert "\x1b" not in out.getvalue()


@pytest.mark.parametrize("arguments", [
    ["--scope", "project-account"], ["--workspace-key", "project:example"],
    ["--tasks-workspace-key", "project:example"], ["--partition", "gpu-standard"],
    ["--storage-workspace-key", "org:example"], ["--limit", "100"], ["--states", "R"],
])
def test_removed_workbench_selectors_are_rejected(arguments):
    with pytest.raises(SystemExit) as rejected:
        build_parser().parse_args(["tui", *arguments])
    assert rejected.value.code == 2


@pytest.mark.parametrize("command", [["status", "--format", "tui"], []])
def test_summary_without_credentials_does_not_start_device_authorization(tmp_path, command):
    with http_endpoint(lambda *_: pytest.fail("summary must not start login")) as (origin, calls):
        out, err = StringIO(), StringIO()
        rc = main([*command, "--site", "site-a", "--base-url", origin],
                  environ={"XDG_CONFIG_HOME": str(tmp_path), "SAI_CREDENTIAL_CACHE": str(tmp_path / "empty")},
                  stdout=out, stderr=err)
    assert rc == 3 and out.getvalue() == ""
    assert "sai auth login" in err.getvalue() and not calls


@pytest.mark.parametrize("terminal", [True, False])
def test_bare_entry_reads_one_business_summary_for_terminal_or_pipe(tmp_path, monkeypatch, terminal):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(builtins, "input", lambda *a: pytest.fail("summary must not prompt"))
    monkeypatch.setattr(cli_module, "_load_ui_console", lambda: pytest.fail("bare entry needs no UI dependency"))
    def reply(call, _):
        parsed = urlsplit(call["path"])
        assert parsed.path == "/v1/account/cli/overview"
        assert parse_qs(parsed.query) == {"site_id": ["site-a"]}
        return 200, sample()
    with http_endpoint(reply) as (origin, calls):
        out, err = StringIO(), StringIO()
        monkeypatch.setattr(out, "isatty", lambda: terminal)
        rc = main([], environ={"SAI_TOKEN": "test-bearer", "SAI_API_BASE_URL": origin,
                  "SAI_SITE_ID": "site-a", "XDG_CONFIG_HOME": str(tmp_path)}, stdout=out, stderr=err)
    assert rc == 0 and not err.getvalue(), err.getvalue()
    assert len(calls) == 1 and calls[0]["method"] == "GET"
    if terminal:
        assert "组织共享" in out.getvalue() and "¥1,280.50" in out.getvalue()
        assert "未读消息  4 条" in out.getvalue() and "\x1b" not in out.getvalue()
    else:
        assert json.loads(out.getvalue())["funds"]["net_balance"] == "1280.50000000"


def test_tui_rejects_redirected_output_before_authentication(tmp_path):
    with http_endpoint(lambda *_: pytest.fail("nonterminal UI must not call HTTP")) as (origin, calls):
        out, err = StringIO(), StringIO()
        assert main(["tui", "--base-url", origin], stdout=out, stderr=err, environ={}) == 2
        assert not out.getvalue() and "interactive terminal" in err.getvalue() and not calls


@pytest.mark.parametrize('missing',['rich','textual'])
def test_missing_optional_ui_package_has_install_hint(missing):
    import subprocess
    import sys
    from pathlib import Path
    source=str(Path(__file__).resolve().parents[1]/'src')
    code='''
import sys
from io import StringIO
sys.path.insert(0,sys.argv[1])
import builtins
original_import=builtins.__import__
def without_dependency(name,*args,**kwargs):
    if name.split('.')[0]==sys.argv[2]:
        raise ModuleNotFoundError(name=sys.argv[2])
    return original_import(name,*args,**kwargs)
builtins.__import__=without_dependency
from sai_cli.cli import main
out,err=StringIO(),StringIO()
out.isatty=lambda:True
sys.stdin.isatty=lambda:True
rc=main(['tui'],environ={},stdout=out,stderr=err)
assert rc==2 and not out.getvalue()
assert "pipx install --force 'WHEEL_PATH[tui]'" in err.getvalue(),err.getvalue()
'''
    subprocess.run([sys.executable,'-I','-B','-c',code,source,missing],check=True,timeout=10)
