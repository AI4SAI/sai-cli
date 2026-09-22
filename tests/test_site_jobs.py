from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json

import pytest

from sai_cli.contracts import JOB_ITEM_FIELDS, JobItem
from sai_cli.errors import ContractError
from sai_cli.render import render_json, render_site_allocation, render_site_jobs
from sai_cli.site_jobs import SiteJobAllocationResult, SiteJobResult


@pytest.fixture
def site_jobs_payload(job_payload):
    return {
        "schema_version": "jobs/v1",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "self",
        "subject": {"slurm_user": "alice", "slurm_account": None},
        "freshness": {
            "source": "squeue",
            "observed_at": "2026-07-31T01:01:00Z",
            "ttl_seconds": 5,
            "age_seconds": 1,
            "stale": False,
        },
        "etag": "a" * 64,
        "has_more": False,
        "items": deepcopy(job_payload["items"]),
    }


def test_site_jobs_preserves_gateway_json_without_inventing_portal_fields(site_jobs_payload):
    result = SiteJobResult.from_payload(site_jobs_payload, request_id="gateway-request")
    assert result.as_dict() == site_jobs_payload
    assert isinstance(result.items, tuple)
    assert json.loads(render_json(result.as_dict())) == site_jobs_payload
    assert "visibility_role" not in result.as_dict()
    assert "count" not in result.as_dict()
    with pytest.raises(FrozenInstanceError):
        result.has_more = True


def test_site_jobs_recursively_allowlists_fields(site_jobs_payload):
    payload = deepcopy(site_jobs_payload)
    for row in (payload, payload["subject"], payload["freshness"], payload["items"][0]):
        row["raw_secret"] = {"token": "must-not-render"}
    result = SiteJobResult.from_payload(payload, request_id="gateway-redacted")
    assert result.as_dict() == site_jobs_payload
    assert set(result.items[0].as_dict()) == set(JOB_ITEM_FIELDS)
    assert "must-not-render" not in render_json(result.as_dict())


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(schema_version="jobs/v2"),
    lambda p: p.pop("subject"),
    lambda p: p.update(scope_type="all"),
    lambda p: p.update(site_id="site-a\n"),
    lambda p: p.update(etag="a" * 63),
    lambda p: p.update(has_more=1),
    lambda p: p.update(items=p["items"] * 501),
    lambda p: p["subject"].pop("slurm_account"),
    lambda p: p["subject"].update(slurm_user=None),
    lambda p: p["subject"].update(slurm_account="personal-alice"),
    lambda p: p["items"][0].update(slurm_user="bob"),
    lambda p: p["items"][0].update(slurm_account=None),
    lambda p: p["items"][0].update(slots=True),
    lambda p: p["items"][0].update(nodes=-1),
    lambda p: p["items"][0].update(state_label={"raw": "state"}),
    lambda p: p["items"][0].update(name="unsafe\x1b[31m"),
    lambda p: p["items"][0].update(reason_or_nodelist="unsafe\x9b31m"),
    lambda p: p["items"][0].update(name="x" * 4097),
    lambda p: p["items"][0].update(submit_time="not-a-date"),
    lambda p: p["items"][0].update(start_time="2026-07-31T08:00:00+08:00"),
    lambda p: p["freshness"].update(source="sacct"),
    lambda p: p["freshness"].update(observed_at="2026-02-30T00:00:00Z"),
    lambda p: p["freshness"].update(observed_at="2026-07-31T08:00:00+08:00"),
    lambda p: p["freshness"].update(observed_at="2026-07-31T00:00:00." + "0" * 64 + "Z"),
    lambda p: p["freshness"].update(age_seconds=True),
    lambda p: p["freshness"].update(ttl_seconds=-1),
    lambda p: p["freshness"].update(stale=True),
])
def test_site_jobs_rejects_malformed_or_out_of_scope_data(site_jobs_payload, mutate):
    mutate(site_jobs_payload)
    with pytest.raises(ContractError) as failure:
        SiteJobResult.from_payload(site_jobs_payload, request_id="gateway-invalid")
    assert failure.value.request_id == "gateway-invalid"
    assert "unsafe" not in str(failure.value)


def test_gateway_long_text_and_zero_ttl_keep_native_semantics(site_jobs_payload):
    site_jobs_payload["items"][0].update(name="n" * 4096, reason_or_nodelist="r" * 4096)
    site_jobs_payload["freshness"].update(ttl_seconds=0, age_seconds=0, stale=True)
    result = SiteJobResult.from_payload(site_jobs_payload, request_id="gateway-native")
    assert result.as_dict() == site_jobs_payload
    assert "..." in render_site_jobs(result)
    with pytest.raises(ContractError):
        JobItem.from_payload(site_jobs_payload["items"][0], request_id="portal-unchanged")


def test_account_subject_requires_the_full_user_account_intersection(site_jobs_payload):
    site_jobs_payload["scope_type"] = "project_account"
    site_jobs_payload["subject"]["slurm_account"] = "project-example"
    site_jobs_payload["items"][0]["slurm_account"] = "project-example"
    SiteJobResult.from_payload(site_jobs_payload, request_id="compound-subject")
    for field, wrong in (("slurm_user", "bob"), ("slurm_account", "other-account")):
        wrong_payload = deepcopy(site_jobs_payload)
        wrong_payload["items"][0][field] = wrong
        with pytest.raises(ContractError):
            SiteJobResult.from_payload(wrong_payload, request_id="subject-overread")
    site_jobs_payload["subject"]["slurm_user"] = None
    SiteJobResult.from_payload(site_jobs_payload, request_id="account-subject")
    site_jobs_payload["subject"]["slurm_account"] = None
    with pytest.raises(ContractError):
        SiteJobResult.from_payload(site_jobs_payload, request_id="missing-account")


@pytest.mark.parametrize("override", [
    {"site_id": "other-site"},
    {"cluster_id": "other-cluster"},
    {"scope": "org_account"},
    {"partition": "other-partition"},
    {"states": ("PD",)},
    {"expected_source": "scontrol"},
    {"account_name": "other-account"},
])
def test_site_job_binding_rejects_request_filter_expansion(site_jobs_payload, override):
    result = SiteJobResult.from_payload(site_jobs_payload, request_id="gateway-bind")
    request = dict(site_id="site-a", cluster_id="cluster-a", scope="self", request_id="gateway-bind",
                   partition="gpu-standard", states=("R",), limit=1, expected_source="squeue")
    result.require_request_binding(**request)
    with pytest.raises(ContractError):
        result.require_request_binding(**{**request, **override})
    site_jobs_payload["items"] *= 2
    with pytest.raises(ContractError):
        SiteJobResult.from_payload(site_jobs_payload, request_id="limit").require_request_binding(**request)


def test_detail_binding_requires_one_exact_job_and_no_truncation(site_jobs_payload):
    site_jobs_payload["freshness"]["source"] = "scontrol"
    request = dict(site_id="site-a", cluster_id="cluster-a", scope="self", request_id="detail",
                   job_id="12345", expected_source="scontrol")
    SiteJobResult.from_payload(site_jobs_payload, request_id="detail").require_request_binding(**request)
    for mutate in (
        lambda p: p.update(items=[]),
        lambda p: p.update(items=p["items"] * 2),
        lambda p: p.update(has_more=True),
        lambda p: p["items"][0].update(job_id="12345_1"),
    ):
        payload = deepcopy(site_jobs_payload)
        mutate(payload)
        with pytest.raises(ContractError):
            SiteJobResult.from_payload(payload, request_id="detail").require_request_binding(**request)


@pytest.mark.parametrize("requested,returned", [("RUNNING", "R"), ("PENDING", "PD"), ("CONFIGURING", "CONFIGURING")])
def test_state_binding_accepts_documented_native_aliases_only(site_jobs_payload, requested, returned):
    site_jobs_payload["items"][0]["state"] = returned
    result = SiteJobResult.from_payload(site_jobs_payload, request_id="states")
    request = dict(site_id="site-a", cluster_id="cluster-a", scope="self", request_id="states", states=(requested,))
    result.require_request_binding(**request)
    assert result.as_dict()["items"][0]["state"] == returned
    site_jobs_payload["items"][0]["state"] = "F"
    with pytest.raises(ContractError):
        SiteJobResult.from_payload(site_jobs_payload, request_id="states").require_request_binding(**request)


def test_gateway_table_shows_observation_and_truncation_without_guessing(site_jobs_payload):
    site_jobs_payload.update(items=[], has_more=True)
    site_jobs_payload["freshness"].update(age_seconds=5, stale=True)
    table = render_site_jobs(SiteJobResult.from_payload(site_jobs_payload, request_id="table"))
    for expected in ("Site: site-a", "Cluster: cluster-a", "Scope: self", "Source: squeue",
                     "Observed: 2026-07-31T01:01:00Z", "Age: 5s", "Stale: yes", "Has-more: yes", "(no jobs)"):
        assert expected in table
    assert "Queried:" not in table


def test_allocation_preserves_snapshot_values_and_recursively_drops_unknown_fields(site_allocation_payload):
    payload = deepcopy(site_allocation_payload)
    for row in (payload, payload["job"], payload["subject"], payload["freshness"],
                payload["allocation"], *payload["allocation"]["nodes"]):
        row["raw_secret"] = "must-not-render"
    result = SiteJobAllocationResult.from_payload(payload, request_id="allocation")
    assert result.as_dict() == site_allocation_payload
    assert set(result.as_dict()["job"]) == set(JOB_ITEM_FIELDS)
    table = render_site_allocation(result)
    assert "compute-a" in table and "0" in table and "16384" in table
    assert "Restart count: -" in table and "Allocated CPUs" in table and "Allocated memory (MiB)" in table
    assert "must-not-render" not in table + render_json(result.as_dict())
    for status, nodes in (("not_allocated", []), ("unavailable", None)):
        payload.update(restart_count=0, scheduler_states=["COMPLETED", "COMPLETING"])
        payload["job"]["state"] = "CD"
        payload["allocation"] = {"status": status, "nodes": nodes}
        result = SiteJobAllocationResult.from_payload(payload, request_id="allocation")
        assert result.as_dict()["allocation"] == payload["allocation"]
        assert result.scheduler_states == ("COMPLETED", "COMPLETING")
        assert "Restart count: 0" in render_site_allocation(result)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(schema_version="jobs/v1"),
    lambda p: p.pop("restart_count"),
    lambda p: p.update(restart_count=True),
    lambda p: p.update(restart_count=-1),
    lambda p: p.update(restart_count=65536),
    lambda p: p.update(scheduler_states=[]),
    lambda p: p.update(scheduler_states=["RUNNING"] * 33),
    lambda p: p.update(scheduler_states=["running"]),
    lambda p: p.update(scheduler_states=["PENDING"]),
    lambda p: p.update(scheduler_states=["RUNNING\x1b"]),
    lambda p: p["allocation"].pop("nodes"),
    lambda p: p["allocation"].update(status="unknown"),
    lambda p: p["allocation"].update(status="unavailable"),
    lambda p: p["allocation"].update(status="not_allocated"),
    lambda p: p["allocation"].update(nodes=[]),
    lambda p: p["allocation"].update(nodes=p["allocation"]["nodes"] * 2049),
    lambda p: p["allocation"]["nodes"][0].update(name="x" * 129),
    lambda p: p["allocation"]["nodes"][0].update(name="node\n"),
    lambda p: p["allocation"]["nodes"][0].update(name="node+1"),
    lambda p: p["allocation"]["nodes"][0].update(cpus=True),
    lambda p: p["allocation"]["nodes"][0].update(memory_mib=-1),
    lambda p: p["allocation"]["nodes"][1].update(name="compute-a"),
    lambda p: p["job"].update(slurm_user="bob"),
    lambda p: p["job"].update(job_id="12345_7"),
    lambda p: p["job"].update(array_task_id="[1-3]"),
])
def test_allocation_rejects_invalid_snapshot_contract(site_allocation_payload, mutate):
    mutate(site_allocation_payload)
    with pytest.raises(ContractError):
        SiteJobAllocationResult.from_payload(site_allocation_payload, request_id="invalid-allocation")


def test_allocation_binds_exact_array_task_and_site(site_allocation_payload):
    site_allocation_payload["job"]["array_task_id"] = "7"
    result = SiteJobAllocationResult.from_payload(site_allocation_payload, request_id="array")
    request = dict(site_id="site-a", cluster_id="cluster-a", scope="self",
                   request_id="array", job_id="12345_7", states=("RUNNING",))
    result.require_request_binding(**request)
    for mismatch in ({"job_id": "12345"}, {"job_id": "12345_8"}, {"site_id": "other"},
                     {"cluster_id": "other"}, {"scope": "org_account"}, {"states": ("PD",)}):
        with pytest.raises(ContractError):
            result.require_request_binding(**{**request, **mismatch})
