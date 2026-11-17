from __future__ import annotations

from io import StringIO
import json

import pytest

from sai_cli.client import JobQuery, PortalClient, clean_states
from sai_cli.errors import ConfigError, ContractError


def test_job_query_maps_hyphenated_scope_and_narrowing_filters() -> None:
    query = JobQuery(
        site_id="site-a",
        scope="project-account",
        account_name="project-example",
        states=clean_states("r,pd,r"),
        partition="gpu-standard",
        limit=25,
    )

    assert query.parameters() == {
        "site_id": "site-a",
        "cluster_id": None,
        "scope_type": "project_account",
        "slurm_account_id": None,
        "slurm_account_name": "project-example",
        "states": "PD,R",
        "source_preference": "live",
        "partition": "gpu-standard",
        "limit": 25,
    }


def test_running_estimate_query_reuses_list_scope_and_narrowing_contract() -> None:
    query = JobQuery(
        site_id="site-a",
        cluster_id="cluster-a",
        scope="org-account",
        account_id="account-id",
        states=clean_states("r,pd"),
        partition="gpu-standard",
        limit=12,
    )

    assert query.parameters() == {
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "org_account",
        "slurm_account_id": "account-id",
        "slurm_account_name": None,
        "states": "PD,R",
        "source_preference": "live",
        "partition": "gpu-standard",
        "limit": 12,
    }


@pytest.mark.parametrize("scope", ["personal-account", "org-account", "project-account"])
def test_account_scopes_require_selector(scope: str) -> None:
    with pytest.raises(ConfigError, match="requires"):
        JobQuery(site_id="site-a", scope=scope).parameters()


def test_self_scope_rejects_account_and_detail_partition() -> None:
    with pytest.raises(ConfigError, match="does not accept"):
        JobQuery(site_id="site-a", scope="self", account_name="unexpected").parameters()
    with pytest.raises(ConfigError, match="does not accept a partition"):
        JobQuery(site_id="site-a", partition="gpu-standard").parameters(detail=True)


def test_invalid_filters_and_limit_are_rejected() -> None:
    with pytest.raises(ConfigError, match="states"):
        clean_states("R,not valid")
    with pytest.raises(ConfigError, match="between 1 and 500"):
        JobQuery(site_id="site-a", limit=0).parameters()
    with pytest.raises(ConfigError, match="account is invalid"):
        JobQuery(site_id="site-a", scope="org-account", account_name="org+invalid").parameters()
    with pytest.raises(ConfigError, match="account is invalid"):
        JobQuery(site_id="site-a", scope="org-account", account_name="a" * 65).parameters()


def test_capability_request_uses_strict_json_shape() -> None:
    query = JobQuery(
        site_id="site-a",
        cluster_id="cluster-a",
        scope="project-account",
        account_name="project-example",
        states=clean_states("pd,r"),
        partition="gpu-standard",
        limit=25,
    )

    assert query.capability_request(operation="jobs.list") == {
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "project_account",
        "slurm_account_id": None,
        "slurm_account_name": "project-example",
        "partition": "gpu-standard",
        "states": ["PD", "R"],
        "job_id": None,
        "limit": 25,
    }


def test_capability_request_rejects_missing_cluster() -> None:
    with pytest.raises(ConfigError, match="cluster"):
        JobQuery(site_id="site-a").capability_request(operation="jobs.list")


@pytest.mark.parametrize("kind", ["personal", "org", "project"])
def test_workspace_selector_preserves_business_identity_for_server_resolution(kind):
    workspace = f"{kind}:owner-example"
    query = JobQuery(site_id="site-a", cluster_id="cluster-a", scope=kind + "-account",
                     workspace_key=workspace)
    for request in (query.parameters(), query.capability_request(operation="jobs.list")):
        assert request["workspace_key"] == workspace
        assert request["scope_type"] == kind + "_account"
        assert request["slurm_account_id"] is None and request["slurm_account_name"] is None
    assert query.validated().workspace_key == workspace


@pytest.mark.parametrize("scope,workspace,selector", [
    ("self", "project:owner-example", {}),
    ("org-account", "project:owner-example", {}),
    ("project-account", "project:owner-example", {"account_id": "native-account-example"}),
    ("project-account", "project:owner-example", {"account_name": "project-example"}),
    ("project-account", "project:../other", {}),
])
def test_workspace_selector_rejects_conflicting_or_invalid_scope(scope, workspace, selector):
    with pytest.raises(ConfigError):
        JobQuery(site_id="site-a", scope=scope, workspace_key=workspace, **selector).parameters()


@pytest.mark.parametrize("task", ["0", "7"])
def test_central_show_binds_exact_canonical_array_identity(job_payload, task, monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    from sai_cli.auth import TokenLease
    from sai_cli.transport import JsonTransport
    from test_site_transport import http_endpoint
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    job_payload["items"][0]["array_task_id"] = task
    with http_endpoint(lambda *_: (200, job_payload)) as (origin, requests):
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2), token_provider=SimpleNamespace(
            get=lambda: TokenLease("test-token", None, "environment")))
        query = JobQuery(site_id="site-a", cluster_id="cluster-a")
        assert client.show_job(f"12345_{task}", query).items[0].canonical_id == f"12345_{task}"
        for wrong in ("12345", "12345_8"):
            with pytest.raises(ContractError):
                client.show_job(wrong, query)
        job_payload["items"][0].update(job_id=f"12345_{task}", array_task_id=None)
        assert client.show_job(f"12345_{task}", query).items[0].canonical_id == f"12345_{task}"
    assert urlsplit(requests[0]["path"]).path == f"/v1/slurm/jobs/12345_{task}"


@pytest.mark.parametrize("target,expected", [("account-research", None), (None, "account-research")])
@pytest.mark.parametrize("failure,exit_code", [("disconnect", 8), ("unavailable", 6), ("malformed", 7)])
def test_uncertain_default_write_recovers_original_acceptance_with_same_intent(
    tmp_path, monkeypatch, target, expected, failure, exit_code,
):
    from sai_cli.cli import main
    from test_default_account import acceptance
    from test_site_transport import http_endpoint
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    saved, accepted, changes = [expected], {}, []

    def reply(call, count):
        assert call["method"] == "PUT" and call["path"] == "/v1/account/cli/defaults"
        assert call["body"] == {"account_id": target, "expected_account_id": expected}
        key = call["idempotency_key"]
        if key not in accepted:
            assert saved[0] == expected
            changes.append(call["body"])
            saved[0] = target
            accepted[key] = acceptance(call)
        if count == 1:
            if failure == "disconnect":
                raise ConnectionResetError("simulated response loss after commit")
            return (503, {"detail": {"code": "service_unavailable"}}) if failure == "unavailable" else (200, {})
        return 200, accepted[key]

    with http_endpoint(reply) as (origin, calls):
        env = {"SAI_TOKEN": "identity-user-token", "XDG_CONFIG_HOME": str(tmp_path / "config")}
        command = ["account", "set-default", target or "auto", "--if-current", expected or "auto",
                   "--request-id", "request-example-one", "--base-url", origin]
        output, error = StringIO(), StringIO()
        assert main(command, environ=env, stdout=output, stderr=error) == exit_code
        assert output.getvalue() == "" and len(calls) == len(changes) == 1
        recovery = json.loads(error.getvalue())["error"]["recovery"]["argv"]
        assert recovery[:8] == ["sai", *command[:7]]
        assert "--site" not in recovery and recovery[recovery.index("--base-url") + 1] == origin
        saved[0] = "account-later"
        output, error = StringIO(), StringIO()
        assert main(recovery[1:], environ=env, stdout=output, stderr=error) == 0, error.getvalue()
        assert json.loads(output.getvalue()) == accepted["request-example-one"]
        assert saved == ["account-later"] and len(changes) == 1 and len(calls) == 2


@pytest.mark.parametrize("status", [400, 403, 409])
def test_rejected_default_write_is_not_an_unknown_outcome(tmp_path, status, monkeypatch):
    from test_default_account import invoke
    from test_site_transport import http_endpoint
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    with http_endpoint(lambda *_: (status, {"detail": {"code": "default_account_changed"}})) as (origin, calls):
        code, output, error = invoke(tmp_path, origin, ["account", "set-default", "account-research",
            "--if-current", "auto", "--request-id", "request-example-one"])
        assert code != 0 and not output and len(calls) == 1
        assert "recovery" not in json.loads(error)["error"] and "unknown" not in error
