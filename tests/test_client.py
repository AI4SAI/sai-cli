from __future__ import annotations

import pytest

from sai_cli.client import JobQuery, clean_states
from sai_cli.errors import ConfigError


def test_job_query_maps_exact_list_capability_request() -> None:
    query = JobQuery(
        site_id="site-a",
        cluster_id="cluster-a",
        scope="project-account",
        account_name="project-example",
        states=clean_states("r,pd,r"),
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


def test_detail_and_running_estimate_use_distinct_operation_shapes() -> None:
    query = JobQuery(
        site_id="site-a",
        cluster_id="cluster-a",
        scope="org-account",
        account_id="account-id",
        states=clean_states("r,pd"),
        partition="gpu-standard",
    )

    detail = JobQuery(
        site_id="site-a",
        cluster_id="cluster-a",
        scope="org-account",
        account_id="account-id",
        states=clean_states("r,pd"),
    ).capability_request(operation="jobs.detail", job_id="123_4")
    assert detail["job_id"] == "123_4"
    assert detail["partition"] is None
    assert detail["limit"] is None

    running = query.capability_request(operation="billing.running-estimate")
    assert running["job_id"] is None
    assert running["partition"] == "gpu-standard"
    assert running["limit"] is None


@pytest.mark.parametrize("scope", ["personal-account", "org-account", "project-account"])
def test_account_scopes_require_selector(scope: str) -> None:
    with pytest.raises(ConfigError, match="requires"):
        JobQuery(
            site_id="site-a",
            cluster_id="cluster-a",
            scope=scope,
        ).capability_request(operation="jobs.list")


def test_self_scope_rejects_account_and_detail_partition() -> None:
    with pytest.raises(ConfigError, match="does not accept"):
        JobQuery(
            site_id="site-a",
            cluster_id="cluster-a",
            account_name="unexpected",
        ).capability_request(operation="jobs.list")
    with pytest.raises(ConfigError, match="does not accept a partition"):
        JobQuery(
            site_id="site-a",
            cluster_id="cluster-a",
            partition="gpu-standard",
        ).capability_request(operation="jobs.detail", job_id="123")


def test_invalid_filters_cluster_and_limit_are_rejected() -> None:
    with pytest.raises(ConfigError, match="states"):
        clean_states("R,not valid")
    with pytest.raises(ConfigError, match="cluster is required"):
        JobQuery(site_id="site-a", cluster_id="").capability_request(
            operation="jobs.list"
        )
    with pytest.raises(ConfigError, match="between 1 and 500"):
        JobQuery(site_id="site-a", cluster_id="cluster-a", limit=0).capability_request(
            operation="jobs.list"
        )
    with pytest.raises(ConfigError, match="account is invalid"):
        JobQuery(
            site_id="site-a",
            cluster_id="cluster-a",
            scope="org-account",
            account_name="org/invalid",
        ).capability_request(operation="jobs.list")
