from copy import deepcopy

import pytest

from sai_cli.contracts import JobItem
from sai_cli.errors import ContractError
from sai_cli.managed_runs import ManagedRunDetail
from sai_cli.run_activity import matching_job
from sai_cli.site_jobs import SiteJobResult
from test_managed_runs_contract import sample


def linked_documents(job_payload):
    detail = sample("detail")
    detail["run"].update(run_link="a" * 64, cluster_id="cluster-a", scheduler_ref="12345",
        status="queued", accepted_at="2026-07-31T00:00:00Z", finished_at=None)
    job = deepcopy(job_payload["items"][0])
    job["run_link"] = "a" * 64
    native = {"schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a", "scope_type": "self",
        "subject": {"slurm_user": "alice", "slurm_account": None},
        "freshness": {"source": "squeue", "observed_at": "2026-07-31T01:01:00Z", "ttl_seconds": 5,
                      "age_seconds": 0, "stale": False},
        "etag": "b" * 64, "items": [job], "has_more": False}
    return detail, native


@pytest.mark.parametrize("change", [None, "number_only", "other_key", "number", "site", "cluster", "stale",
    "older_submission", "after_finish", "array_zero", "no_submission", "ambiguous"])
def test_correlation_needs_identity_time_and_one_current_observation(job_payload, change):
    detail, native = linked_documents(job_payload)
    run, job = detail["run"], native["items"][0]
    if change == "number_only": del job["run_link"]
    elif change == "other_key": job["run_link"] = "c" * 64
    elif change == "number": job["job_id"] = "12346"
    elif change == "site": native["site_id"] = "site-b"
    elif change == "cluster": native["cluster_id"] = "cluster-b"
    elif change == "stale": native["freshness"].update(age_seconds=6, stale=True)
    elif change == "older_submission": job["submit_time"] = "2026-07-30T00:00:00Z"
    elif change == "after_finish": run["finished_at"] = "2026-07-31T00:00:30Z"
    elif change == "array_zero": job["array_task_id"] = "0"
    elif change == "no_submission": job["submit_time"] = None
    elif change == "ambiguous": native["items"].append({**job, "job_id": "12346"})
    read = SiteJobResult.from_payload(native, request_id="native")
    matched = matching_job(run, read, site_id="site-a")
    assert (matched is not None) == (change is None)
    if matched:
        assert matched.values["state"] == "R" and run["status"] == "queued"


@pytest.mark.parametrize("value", ["", "a" * 63, "A" * 64, "f" * 64 + "\n", 1, False, {}])
def test_run_link_remains_a_typed_allowlisted_value(job_payload, value):
    detail, native = linked_documents(job_payload)
    detail["run"]["run_link"] = native["items"][0]["run_link"] = value
    with pytest.raises(ContractError):
        JobItem.from_payload(native["items"][0], request_id="invalid")
    with pytest.raises(ContractError):
        ManagedRunDetail.from_payload(detail, workspace_key=detail["workspace_key"], site_id=detail["site_id"],
            run_ref=detail["run"]["run_ref"], request_id="invalid")
