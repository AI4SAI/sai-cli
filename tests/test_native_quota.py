from __future__ import annotations

from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import time

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.native_quota import NativeQuotaResult
from test_cli_integration import _env, _server


def native_payload():
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/storage-native-quota/v1/sample.json").read_text())


def test_native_quota_exact_counters_and_recursive_redaction():
    payload = native_payload()
    payload["items"][0]["used_bytes"] = str(9007199254740993 * 1024)
    payload["path"] = "/private"
    payload["items"][0].update(project_id=123, native={"token": "secret"})
    result = NativeQuotaResult.from_payload(payload, site_id="site-a", workspace_key="project:example", request_id="r")
    assert result.values["items"][0]["used_bytes"] == "9223372036854776832"
    assert "secret" not in json.dumps(result.as_dict())
    assert "project_id" not in result.as_dict()["items"][0]
    result.as_dict()["items"][0]["used_bytes"] = "0"
    assert result.values["items"][0]["used_bytes"] != "0"


@pytest.mark.parametrize("change", [
    lambda p: p.update(source="portal_quota_observation"),
    lambda p: p.update(workspace_key="org:another"),
    lambda p: p.update(site_id="site-b"),
    lambda p: p.update(items=[]),
    lambda p: p.update(items=p["items"] * 2),
    lambda p: p["items"][0].update(used_bytes=2**63),
    lambda p: p["items"][0].update(used_bytes="1e3"),
    lambda p: p["items"][0].update(inode_hard=None),
    lambda p: p["items"][0].update(used_inodes=str(2**64)),
    lambda p: p["items"][0].update(label="unsafe\x1b[31m"),
    lambda p: p["items"][0].update(observed_at="2026-09-23T00:00:00+08:00"),
])
def test_native_quota_rejects_wrong_scope_inaccurate_or_unsafe_data(change):
    payload = native_payload(); change(payload)
    with pytest.raises(ContractError):
        NativeQuotaResult.from_payload(payload, site_id="site-a", workspace_key="project:example", request_id="r")


@pytest.mark.parametrize("prefix,output_format", [(True, "json"), (False, "table")])
def test_native_quota_cli_capability_only_http(tmp_path, monkeypatch, prefix, output_format):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    capability = {
        "schema_version": "sai-storage-read-capability/v1", "capability": "opaque-storage-token",
        "expires_at": int(time.time()) + 120, "audience": "sai-site-read", "surface": "site-read",
        "operation": "storage.quota.read", "workspace_key": "project:example", "site_id": "site-a",
    }
    with _server(capability) as (issuer_url, issuer), _server(native_payload()) as (gateway_url, gateway):
        config = tmp_path / "config.toml"
        config.write_text(f'[profiles.default]\nbase_url="{issuer_url}"\nsite_id="site-a"\ncluster_id="cluster-a"\nrequire_site_capability=true\nsite_read_base_url="{gateway_url}"\n')
        config.chmod(0o600)
        options = ["--config", str(config), "--site", "site-a"]
        command = ["storage", "native-quota", "--workspace-key", "project:example", "--format", output_format]
        output, errors = StringIO(), StringIO()
        assert main(options + command if prefix else command + options,
                    environ=_env(tmp_path), stdout=output, stderr=errors) == 0, errors.getvalue()
        assert issuer.requests[0]["path"] == "/v1/authz/storage-read"
        assert issuer.requests[0]["body"] == {"workspace_key": "project:example", "site_id": "site-a"}
        assert issuer.requests[0]["authorization"] == "Bearer test-bearer-token"
        assert len(gateway.requests) == 1
        assert gateway.requests[0]["path"] == "/v1/site-read/storage/native-quota"
        assert gateway.requests[0]["query"] == {}
        assert gateway.requests[0]["authorization"] is None
        assert gateway.requests[0]["capability"] == "opaque-storage-token"
        if output_format == "json":
            assert json.loads(output.getvalue()) == native_payload()
        else:
            assert "not an organization pool total" in output.getvalue()
        gateway.response_status = 503
        gateway.response_payload = {"detail": {"private": "secret"}}
        output, errors = StringIO(), StringIO()
        assert main(command + options, environ=_env(tmp_path), stdout=output, stderr=errors) == 6
        assert output.getvalue() == "" and "secret" not in errors.getvalue()
        assert all(row["path"] == "/v1/authz/storage-read" for row in issuer.requests)


def test_native_quota_without_direct_transport_does_not_query_portal(tmp_path):
    with _server(native_payload()) as (url, server):
        output, errors = StringIO(), StringIO()
        result = main(["storage", "native-quota", "--workspace-key", "project:example", "--base-url", url, "--site", "site-a"],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
        assert result != 0 and server.requests == [] and output.getvalue() == ""
