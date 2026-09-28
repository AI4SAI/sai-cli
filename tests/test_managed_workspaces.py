from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import build_parser, main
from sai_cli.errors import ContractError
from sai_cli.managed_runs import ManagedRunWorkspaces
from test_cli_integration import _env, _server


def sample():
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/managed-workspaces/v1/sample.json").read_text())


def parse(data, *, cursor=None, limit=50):
    return ManagedRunWorkspaces.from_payload(data, site_id="site-a", cursor=cursor, limit=limit, request_id="choices")


def test_choice_projection_drops_private_fields_and_rejects_invalid_pages():
    expected = sample()
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
        {"schema_version": "compute.workspaces/v2"}, {"site_id": "site-other"},
        {"queried_at": "not-a-time"}, {"has_more": 1},
        {"next_cursor": "project:project-example", "has_more": False},
        {"items": [], "has_more": True, "next_cursor": "project:project-example"},
        {"items": expected["items"] * 2},
    ]
    for fields in changes:
        with pytest.raises(ContractError): parse({**expected, **fields})
    for fields in ({"label": "\x1b[2J"}, {"label": "\x85"}, {"label": "x" * 257},
                   {"workspace_key": "org:example"}, {"workspace_key": "project:a+b"},
                   {"organization_label": []}):
        changed = deepcopy(expected); changed["items"][0].update(fields)
        with pytest.raises(ContractError): parse(changed)
    with pytest.raises(ContractError): parse(expected, cursor="project:project-example")
    with pytest.raises(ContractError): parse(expected, limit=0)
    # Duplicate display labels are valid; identity and pagination use keys only.
    data = deepcopy(expected)
    data["items"].append({**data["items"][0], "workspace_key": "project:second"})
    data.update(next_cursor="project:second", has_more=True)
    assert len(parse(data).values["items"]) == 2
    data["next_cursor"] = "project:first"
    with pytest.raises(ContractError): parse(data)


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
def test_workspace_discovery_is_narrow_identity_http_in_both_argument_positions(tmp_path, prefix, output_format):
    body = sample()
    with _server(body) as (origin, server):
        connection = ["--site", "site-a", "--base-url", origin]
        command = ["runs", "workspaces", "--cursor", "project:older", "--limit", "10", "--format", output_format]
        stdout, stderr = StringIO(), StringIO()
        result = main(connection + command if prefix else command + connection,
            environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1"}, stdout=stdout, stderr=stderr)
    assert result == 0, stderr.getvalue()
    assert stderr.getvalue() == "" and len(server.requests) == 1
    request = server.requests[0]
    assert request["path"] == "/v1/compute/cli/workspaces"
    assert request["query"] == {"site_id": ["site-a"], "cursor": ["project:older"], "limit": ["10"]}
    assert request["authorization"] == "Bearer test-bearer-token" and request["capability"] is None
    if output_format == "json": assert json.loads(stdout.getvalue()) == body
    else: assert body["items"][0]["label"] in stdout.getvalue()


@pytest.mark.parametrize("arguments", [["--cursor", "org:other"], ["--limit", "101"], ["--cluster", "cluster-a"],
                                      ["--site", ".site"], ["--site", "_site"], ["--site", "GLOBAL"], ["--site", "default"]])
def test_invalid_discovery_filters_send_no_request(tmp_path, arguments):
    with _server(sample()) as (origin, server):
        stdout, stderr = StringIO(), StringIO()
        code = main(["runs", "workspaces", "--site", "site-a", "--base-url", origin, *arguments],
                    environ=_env(tmp_path), stdout=stdout, stderr=stderr)
    assert code == 2 and stdout.getvalue() == "" and server.requests == []


def test_workbench_language_is_explicit_and_batch_json_unchanged():
    assert build_parser().parse_args(["tui"]).language == "zh-CN"
    assert build_parser().parse_args(["tui", "--language", "en-US"]).language == "en-US"
