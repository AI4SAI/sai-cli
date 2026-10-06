"""The terminal entry answers one SAI question without opening a workbench."""
from io import StringIO
import builtins
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import build_parser, main
from test_overview import sample
from test_site_transport import http_endpoint


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("language,label", [("zh-CN", "组织共享"), ("en-US", "Shared")])
def test_tui_reads_one_summary_and_returns_without_input(tmp_path, monkeypatch, prefix, language, label):
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
        command = ["tui", "--language", language]
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


def test_tui_without_credentials_does_not_start_device_authorization(tmp_path):
    with http_endpoint(lambda *_: pytest.fail("summary must not start login")) as (origin, calls):
        out, err = StringIO(), StringIO()
        rc = main(["tui", "--site", "site-a", "--base-url", origin],
                  environ={"XDG_CONFIG_HOME": str(tmp_path), "SAI_CREDENTIAL_CACHE": str(tmp_path / "empty")},
                  stdout=out, stderr=err)
    assert rc == 3 and out.getvalue() == ""
    assert "sai auth login" in err.getvalue() and not calls
