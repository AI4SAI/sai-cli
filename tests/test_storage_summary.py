from __future__ import annotations

from copy import deepcopy
import json
from io import StringIO
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ConfigError, ContractError
from sai_cli.storage_summary import StorageQuotaSummary, clean_workspace_key
from test_cli_integration import _env, _server


def payload() -> dict:
    path = Path(__file__).resolve().parents[1] / "contracts/storage-quota-summary/v1/sample.json"
    result = json.loads(path.read_text())
    result.update(workspace_key="personal:user-1", site_id="site-a")
    return result


def test_storage_summary_preserves_null_state_negative_remaining_and_allowlists():
    value = payload(); value["used_tib"] = None; value["state"] = "pending"
    result = StorageQuotaSummary.from_payload(value, workspace_key="personal:user-1", site_id="site-a", request_id="r")
    assert result.values["used_tib"] is None and result.values["state"] == "pending"
    value["remaining_tib"] = "-1.00000000"
    value.update(path="/private", organization_storage={"can_manage": True}, wallet={"balance": "999"})
    result = StorageQuotaSummary.from_payload(value, workspace_key="personal:user-1", site_id="site-a", request_id="r")
    assert result.values["remaining_tib"] == "-1.00000000"
    assert not {"path", "organization_storage", "wallet"}.intersection(result.as_dict())


@pytest.mark.parametrize("field,value", [
    ("state", "unknown"), ("source", "lfs"), ("used_tib", "1e3"),
    ("used_inodes", True), ("observed_at", "2026-09-23"),
    ("used_inodes", 9007199254740992), ("used_tib", "-1"), ("used_tib", "NaN"),
    ("observed_at", "2026-02-30T00:00:00Z"), ("observed_at", "2026-09-23T00:00Z"),
    ("effective_total_tib", "1\u001b[31m"), ("remaining_tib", "9" * 65),
    ("state", {}), ("state", False), ("mount_id", "unsafe\u009b"),
    ("mount_id", "two words"),
])
def test_storage_summary_rejects_unsafe_or_ambiguous_facts(field, value):
    value_payload = payload(); value_payload[field] = value
    with pytest.raises(ContractError):
        StorageQuotaSummary.from_payload(value_payload, workspace_key="personal:user-1", site_id="site-a", request_id="r")


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
def test_storage_summary_cli_reads_narrow_contract_and_sends_no_site_capability(tmp_path, prefix, output_format):
    body = payload()
    with _server(body) as (origin, server):
        output, errors = StringIO(), StringIO()
        command = (["--site", "site-a", "storage", "quota-summary"] if prefix else
                   ["storage", "quota-summary", "--site", "site-a"])
        result = main([*command, "--base-url", origin, "--workspace-key", "personal:user-1", "--format", output_format],
            environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1"}, stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    if output_format == "json":
        assert json.loads(output.getvalue()) == body
    else:
        assert "Stored observation" in output.getvalue() and body["observed_at"] in output.getvalue()
    assert server.requests[0]["path"] == "/v1/account/cli/storage/quota-summary"
    assert server.requests[0]["query"] == {
        "workspace_key": ["personal:user-1"], "site_id": ["site-a"],
    }
    assert server.requests[0]["capability"] is None
    assert server.requests[0]["authorization"] == "Bearer test-bearer-token"


def test_storage_summary_cli_error_does_not_render_partial_data(tmp_path):
    with _server({"detail": {"code": "quota_unavailable", "message": "Unavailable", "native": "private"}, "path": "/secret"}, status=503) as (origin, _):
        output, errors = StringIO(), StringIO()
        result = main(["storage", "quota-summary", "--base-url", origin,
                       "--site", "site-a", "--workspace-key", "personal:user-1"],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 6 and output.getvalue() == ""
    assert "private" not in errors.getvalue() and "/secret" not in errors.getvalue()


def test_storage_summary_requires_explicit_nullable_fields_and_exact_scope():
    for changed in ({**payload(), "site_id": "other"}, {**payload(), "workspace_key": "org:other"}):
        with pytest.raises(ContractError):
            StorageQuotaSummary.from_payload(changed, workspace_key="personal:user-1", site_id="site-a", request_id="r")
    for field in payload():
        changed = payload(); del changed[field]
        with pytest.raises(ContractError):
            StorageQuotaSummary.from_payload(changed, workspace_key="personal:user-1", site_id="site-a", request_id="r")


@pytest.mark.parametrize("workspace", ["", "self", "all:users", "org:", "personal:user/child", "org:user\n", "org:_id", "org:has.dot"])
def test_storage_workspace_keys_do_not_expand_to_paths(workspace):
    with pytest.raises(ConfigError):
        clean_workspace_key(workspace)


def test_workspace_length_is_bounded_as_a_whole():
    for prefix in ("org:", "project:", "personal:"):
        key = prefix + "a" * (128 - len(prefix))
        assert clean_workspace_key(key) == key
        with pytest.raises(ConfigError):
            clean_workspace_key(key + "b")
