"""Directory discovery preserves server facts and continues empty HTTP pages."""
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import build_parser, main
from sai_cli.discovery import authorization_scopes, describe
from sai_cli.errors import ContractError
from sai_cli.file_workspaces import FileWorkspaces, render_directories
from test_cli_integration import _env, _server
from test_site_transport import http_endpoint


CURSOR = "workspace-example~" + "a" * 64


def sample():
    root = Path(__file__).resolve().parents[1]/"contracts/file-workspace-discovery/v1"
    return {**json.loads((root/"example.json").read_text()), "site_id": "site-a"}


def parse(value, *, cursor=None):
    return FileWorkspaces.from_payload(value, site_id="site-a", limit=50, cursor=cursor, request_id="directory-read")


def test_directory_contract_keeps_path_and_permission_facts_and_drops_unknown_fields():
    value = sample()
    value["items"][0].update(label="result\n\x1b[31m\x85\tname", path="/data/ name 'a' $x `x`/line\n\t\x1b[2J")
    expected = deepcopy(value)
    value["wallet"] = "private-wallet"
    value["items"][0]["credentials"] = "private-token"
    value["items"][0]["actions"]["compute"]["funding_ready"] = True
    parsed = parse(value)
    assert parsed.as_dict() == expected
    assert parsed.values["items"][0]["path_label"] == expected["items"][0]["path_label"]
    output = render_directories(parsed)
    assert "\x1b" not in output and "\x85" not in output and "\t" not in output
    assert r"result\n\x1b[31m\x85\tname" in output
    assert r"line\n\t\x1b[2J" in output and "private" not in output
    assert "needs_project_compute_permission" not in output and "funding_ready" not in output
    exported = parsed.as_dict()
    exported["items"][0]["actions"]["compute"]["allowed"] = True
    assert not parsed.values["items"][0]["actions"]["compute"]["allowed"]


@pytest.mark.parametrize("patch", [
    {"schema_version": "file-workspace-discovery/v2"}, {"site_id": "site-other"},
    {"items": {}}, {"items": [None]}, {"next_cursor": "bad"}, {"next_cursor": []},
])
def test_directory_page_rejects_malformed_scope_or_pagination(patch):
    with pytest.raises(ContractError):
        parse({**sample(), **patch})


def test_directory_items_reject_missing_fields_types_and_contradictory_actions():
    for patch in ({"kind": []}, {"role": True}, {"workspace_ref": "x" * 257}, {"path": "relative"},
                  {"path": "/"}, {"path": "/bad\0path"}, {"label": None}, {"actions": []}):
        value = sample()
        value["items"][0].update(patch)
        with pytest.raises(ContractError):
            parse(value)
    for patch in ({"allowed": 1}, {"reason": []}, {"reason": "wallet_ready"}, {"allowed": True}):
        value = sample()
        value["items"][0]["actions"]["compute"].update(patch)
        with pytest.raises(ContractError):
            parse(value)
    for key in sample()["items"][0]:
        value = sample()
        del value["items"][0][key]
        with pytest.raises(ContractError):
            parse(value)
    with pytest.raises(ContractError):
        parse({**sample(), "next_cursor": CURSOR}, cursor=CURSOR)


@pytest.mark.parametrize("prefix", [False, True])
def test_real_http_empty_page_continues_with_profile_format_site_and_limit(tmp_path, prefix):
    def respond(call, count):
        url = urlsplit(call["path"])
        assert call["method"] == "GET" and url.path == "/v1/account/cli/file-workspaces"
        assert call["bearer"] == "Bearer test-bearer-token" and call["capability"] is None
        assert parse_qs(url.query) == {"site_id": ["site-a"], "limit": ["2"], **({"cursor": [CURSOR]} if count == 2 else {})}
        return 200, {**sample(), "items": [], "next_cursor": CURSOR} if count == 1 else sample()
    with http_endpoint(respond) as (origin, calls):
        config = tmp_path/"profile with spaces.toml"
        config.write_text(f'[profiles.selected]\nbase_url={json.dumps(origin)}\nrequire_site_capability=true\n')
        config.chmod(0o600)
        flags = ["--site", "site-a", "--config", str(config), "--profile", "selected"]
        command = ["storage", "directories", "--limit", "2", "--format", "table"]
        out, err = StringIO(), StringIO()
        assert main(flags+command if prefix else command+flags, environ=_env(tmp_path), stdout=out, stderr=err) == 0, err.getvalue()
        assert not err.getvalue() and "No directories on this page." in out.getvalue()
        follow = shlex.split(out.getvalue().split("Next page: ", 1)[1].strip())
        assert follow[0] == "sai" and "--format" in follow and "selected" in follow
        out = StringIO()
        assert main(follow[1:], environ=_env(tmp_path), stdout=out, stderr=err) == 0, err.getvalue()
        assert sample()["items"][0]["path"] in out.getvalue() and "Next page:" not in out.getvalue()
        assert len(calls) == 2


@pytest.mark.parametrize("status,code,exit_code", [(403, "identity_scope_denied", 4), (503, "directory_unavailable", 6)])
def test_directory_http_denial_has_no_fallback_or_private_body(tmp_path, status, code, exit_code):
    with _server({"detail": {"code": code, "message": "Unavailable", "raw": "private-content"}}, status=status) as (origin, server):
        out, err = StringIO(), StringIO()
        result = main(["storage", "directories", "--site", "site-a", "--base-url", origin],
            environ=_env(tmp_path), stdout=out, stderr=err)
    assert result == exit_code and not out.getvalue() and "private-content" not in err.getvalue()
    assert len(server.requests) == 1 and json.loads(err.getvalue())["error"]["code"] == code


def test_directory_json_and_offline_authorization_discovery(tmp_path):
    with _server(sample()) as (origin, server):
        out, err = StringIO(), StringIO()
        assert main(["storage", "directories", "--site", "site-a", "--base-url", origin],
                    environ=_env(tmp_path), stdout=out, stderr=err) == 0
    assert json.loads(out.getvalue()) == sample() and not err.getvalue() and len(server.requests) == 1
    parser = build_parser()
    operation = describe(parser, ["storage", "directories"])["operations"][0]
    assert operation["source"] == "portal" and operation["effect"] == "read"
    assert operation["required_scopes"] == ["sai.ssh.mounts.read"]
    assert authorization_scopes(parser, ["storage", "directories"]) == ("sai.ssh.mounts.read",)
    assert {item["name"] for item in operation["parameters"]} >= {"site", "limit", "cursor", "format"}


@pytest.mark.parametrize("field,bad", [("kind", []), ("role", {}), ("reason", [])])
def test_malformed_http_enum_types_are_contract_errors(tmp_path, field, bad):
    value = sample()
    target = value["items"][0]["actions"]["compute"] if field == "reason" else value["items"][0]
    target[field] = bad
    with _server(value) as (origin, server):
        out, err = StringIO(), StringIO()
        result = main(["storage", "directories", "--site", "site-a", "--base-url", origin],
            environ=_env(tmp_path), stdout=out, stderr=err)
    assert result == 7 and not out.getvalue() and len(server.requests) == 1
    assert json.loads(err.getvalue())["error"]["code"] == "contract_invalid"


def test_installed_directory_reader_continues_and_surfaces_scope_or_source_failure(tmp_path):
    interpreter = os.environ.get("SAI_TEST_CLI_PYTHON")
    if not interpreter:
        pytest.skip("requires the installed paired CLI wheel")
    responses = [(200, {**sample(), "items": [], "next_cursor": CURSOR}), (200, sample()),
        (403, {"detail": {"code": "identity_scope_denied", "message": "Missing consent"}}),
        (503, {"detail": {"code": "directory_unavailable", "raw": "private-provider-data"}})]
    def respond(call, count):
        assert call["method"] == "GET" and call["capability"] is None
        return responses[count-1]
    with http_endpoint(respond) as (origin, calls):
        command = [interpreter, "-I", "-m", "sai_cli", "storage", "directories", "--site", "site-a", "--base-url", origin]
        env = {**_env(tmp_path), "PATH": "", "NO_PROXY": "127.0.0.1,localhost"}
        first = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
        assert first.returncode == 0, first.stderr
        page = json.loads(first.stdout)
        assert page["items"] == [] and page["next_cursor"] == CURSOR
        second = subprocess.run([*command, "--cursor", page["next_cursor"]], env=env, cwd=tmp_path,
                                capture_output=True, text=True, timeout=15)
        assert second.returncode == 0 and json.loads(second.stdout) == sample(), second.stderr
        for code, expected in ((4, "identity_scope_denied"), (6, "directory_unavailable")):
            result = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
            assert result.returncode == code and not result.stdout
            assert json.loads(result.stderr)["error"]["code"] == expected
            assert "private-provider-data" not in result.stderr
        assert len(calls) == 4
