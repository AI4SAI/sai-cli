from __future__ import annotations

import pytest

from sai_cli.client import JobQuery, clean_states
from sai_cli.errors import ConfigError


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
        "states": "R,PD",
        "source_preference": "live",
        "partition": "gpu-standard",
        "limit": 25,
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
