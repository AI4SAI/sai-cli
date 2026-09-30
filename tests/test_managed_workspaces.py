from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import build_parser, main
from sai_cli.errors import ContractError
from sai_cli.managed_runs import ManagedRunWorkspaces
from sai_cli.storage_summary import StorageWorkspaces
from test_cli_integration import _env, _server


def sample(family="runs"):
    contract = "managed-workspaces" if family == "runs" else "storage-workspaces"
    return json.loads((Path(__file__).resolve().parents[1] / f"contracts/{contract}/v1/sample.json").read_text())


def parse(data, *, cursor=None, limit=50, workspace_key=None):
    model = StorageWorkspaces if data.get("schema_version", "").startswith("storage.") else ManagedRunWorkspaces
    return model.from_payload(data, site_id="site-a", cursor=cursor, limit=limit,
                              workspace_key=workspace_key, request_id="choices")


@pytest.mark.parametrize("family", ["runs", "storage"])
def test_choice_projection_drops_private_fields_and_rejects_invalid_pages(family):
    expected = sample(family)
    expected["items"] = expected["items"][-1:]
    data = deepcopy(expected)
    data["wallet"] = "private"
    data["items"][0].update(path="/private", default_account="private", grants=["private"])
    result = parse(data)
    assert result.as_dict() == expected
    copy = result.as_dict()
    copy["items"][0]["label"] = "changed"
    assert result.values["items"][0]["label"] == expected["items"][0]["label"]
    for field in expected:
        changed = deepcopy(expected); del changed[field]
        with pytest.raises(ContractError): parse(changed)
    for field in expected["items"][0]:
        changed = deepcopy(expected); del changed["items"][0][field]
        with pytest.raises(ContractError): parse(changed)
    changes = [
        {"schema_version": expected["schema_version"].replace("v1", "v2")}, {"site_id": "site-other"},
        {"queried_at": "not-a-time"}, {"queried_at": "2030-02-30T00:00:00Z"}, {"has_more": 1},
        {"items": {}}, {"items": [None]}, {"next_cursor": "all:users"},
        {"next_cursor": "project:project-example", "has_more": False},
        {"items": [], "has_more": True, "next_cursor": "project:project-example"},
        {"items": expected["items"] * 2},
    ]
    for fields in changes:
        with pytest.raises(ContractError): parse({**expected, **fields})
    for fields in ({"label": "\x1b[2J"}, {"label": "\x85"}, {"label": "x" * 257},
                   {"workspace_key": "org:example" if family == "runs" else "all:users"},
                   {"workspace_key": "project:a+b"}, {"organization_label": []},
                   {"organization_label": "\x9bprivate"}, {"label": " "}):
        changed = deepcopy(expected); changed["items"][0].update(fields)
        with pytest.raises(ContractError): parse(changed)
    with pytest.raises(ContractError): parse(expected, cursor="project:project-example")
    for limit in (0, 101, True, 1.5):
        with pytest.raises(ContractError): parse(expected, limit=limit)
    assert parse({**expected, "items": []}).values["items"] == []
    # Duplicate display labels are valid; identity and pagination use keys only.
    data = deepcopy(expected)
    data["items"].append({**data["items"][0], "workspace_key": "project:second"})
    data.update(next_cursor="project:second", has_more=True)
    assert len(parse(data).values["items"]) == 2
    data["next_cursor"] = "project:first"
    with pytest.raises(ContractError): parse(data)


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
@pytest.mark.parametrize("family", ["runs", "storage"])
def test_workspace_discovery_is_narrow_identity_http_in_both_argument_positions(tmp_path, prefix, output_format, family):
    body = sample(family)
    with _server(body) as (origin, server):
        connection = ["--site", "site-a", "--base-url", origin]
        command = [family, "workspaces", "--cursor", "project:older", "--limit", "10", "--format", output_format]
        stdout, stderr = StringIO(), StringIO()
        result = main(connection + command if prefix else command + connection,
            environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1"}, stdout=stdout, stderr=stderr)
    assert result == 0, stderr.getvalue()
    assert stderr.getvalue() == "" and len(server.requests) == 1
    request = server.requests[0]
    assert request["path"] == ("/v1/compute/cli/workspaces" if family == "runs" else "/v1/account/cli/storage/workspaces")
    assert request["query"] == {"site_id": ["site-a"], "cursor": ["project:older"], "limit": ["10"]}
    assert request["authorization"] == "Bearer test-bearer-token" and request["capability"] is None
    if output_format == "json": assert json.loads(stdout.getvalue()) == body
    else: assert body["items"][0]["label"] in stdout.getvalue()


@pytest.mark.parametrize("family", ["runs", "storage"])
@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
def test_exact_workspace_is_one_bound_identity_http_read(tmp_path, family, prefix, output_format):
    body = sample(family)
    body["items"] = body["items"][:1]
    key = body["items"][0]["workspace_key"]
    with _server(body) as (origin, server):
        connection = ["--site", "site-a", "--base-url", origin]
        command = [family, "workspaces", "--workspace-key", key, "--format", output_format]
        stdout, stderr = StringIO(), StringIO()
        code = main(connection + command if prefix else command + connection,
            environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1"}, stdout=stdout, stderr=stderr)
    assert code == 0 and stderr.getvalue() == "" and len(server.requests) == 1
    request = server.requests[0]
    assert request["path"] == ("/v1/compute/cli/workspaces" if family == "runs" else "/v1/account/cli/storage/workspaces")
    assert request["query"] == {"site_id": ["site-a"], "limit": ["50"], "workspace_key": [key]}
    assert request["authorization"] == "Bearer test-bearer-token" and request["capability"] is None
    if output_format == "json": assert json.loads(stdout.getvalue()) == body
    else: assert body["items"][0]["label"] in stdout.getvalue()


@pytest.mark.parametrize("family", ["runs", "storage"])
@pytest.mark.parametrize("fault", ["empty", "other", "multiple", "continued", "schema"])
def test_exact_workspace_rejects_unbound_http_success(tmp_path, family, fault):
    body = sample(family)
    body["items"] = body["items"][:1]
    key = body["items"][0]["workspace_key"]
    if fault == "empty": body["items"] = []
    elif fault == "other": body["items"][0]["workspace_key"] = "project:unrelated"
    elif fault == "multiple": body["items"].append({**body["items"][0], "workspace_key": "project:unrelated"})
    elif fault == "continued": body.update(has_more=True, next_cursor=key)
    else: body["schema_version"] = "storage.workspaces/v1" if family == "runs" else "compute.workspaces/v1"
    with _server(body) as (origin, server):
        stdout, stderr = StringIO(), StringIO()
        code = main([family, "workspaces", "--site", "site-a", "--base-url", origin, "--workspace-key", key],
                    environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 7 and stdout.getvalue() == "" and len(server.requests) == 1
    assert "unrelated" not in stderr.getvalue()


def test_storage_directory_exact_accepts_each_scope_without_deriving_keys_from_names():
    body = sample("storage")
    for row in body["items"]:
        page = {**body, "items": [{**row, "label": "Same / label"}]}
        assert parse(page, workspace_key=row["workspace_key"]).values["items"][0]["workspace_key"] == row["workspace_key"]


@pytest.mark.parametrize("family", ["runs", "storage"])
def test_exact_workspace_denial_never_falls_back_to_discovery(tmp_path, family):
    body = {"detail": {"code": "workspace_read_denied", "message": "Not permitted", "native": "/private"}}
    with _server(body, status=403) as (origin, server):
        stdout, stderr = StringIO(), StringIO()
        code = main([family, "workspaces", "--site", "site-a", "--base-url", origin,
                     "--workspace-key", "project:denied"], environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 4 and stdout.getvalue() == "" and len(server.requests) == 1
    assert "/private" not in stderr.getvalue()


@pytest.mark.parametrize("family", ["runs", "storage"])
@pytest.mark.parametrize("arguments", [["--cursor", "all:other"], ["--limit", "101"], ["--cluster", "cluster-a"],
    ["--site", ".site"], ["--site", "_site"], ["--site", "GLOBAL"], ["--site", "default"],
    ["--workspace-key", "project:first", "--cursor", "project:older"], ["--workspace-key", "all:users"]])
def test_invalid_discovery_filters_send_no_request(tmp_path, arguments, family):
    with _server(sample(family)) as (origin, server):
        stdout, stderr = StringIO(), StringIO()
        code = main([family, "workspaces", "--site", "site-a", "--base-url", origin, *arguments],
                    environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 2 and stdout.getvalue() == "" and server.requests == []


@pytest.mark.parametrize("family,key", [("runs", "org:example"), ("storage", "project:has.dot")])
def test_directory_scope_rules_apply_to_both_cursor_and_exact_key(tmp_path, family, key):
    with _server(sample(family)) as (origin, server):
        for option in ("--cursor", "--workspace-key"):
            stdout, stderr = StringIO(), StringIO()
            code = main([family, "workspaces", "--site", "site-a", "--base-url", origin, option, key],
                        environ=_env(tmp_path), stdout=stdout, stderr=stderr)
            assert code == 2 and stdout.getvalue() == "" and server.requests == []


def test_workbench_language_is_explicit_and_batch_json_unchanged():
    assert build_parser().parse_args(["tui"]).language == "zh-CN"
    assert build_parser().parse_args(["tui", "--language", "en-US"]).language == "en-US"
