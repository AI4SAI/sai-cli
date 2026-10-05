from __future__ import annotations

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
