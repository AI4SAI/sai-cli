"""SAI observations remain separate from the scheduler's native reason."""
from copy import deepcopy
import json
import os
import time

import pytest

from sai_compute_restrictions import normalize_snapshot, read_snapshot, restriction_for_job


def snapshot():
    now = int(time.time())
    return {"schema_version": "sai.compute-restrictions/v1", "cluster_id": "cluster-a",
            "generation": now * 1_000_000, "published_at": now, "expires_at": now + 300,
            "accounts": {
                "org-a": {"lineage": ["root", "org-a"], "group_jobs_limit": 0,
                          "observed_at": now, "reason": "arrears"},
                "project-a": {"lineage": ["root", "org-a", "project-a"],
                              "group_jobs_limit": None, "observed_at": now},
            }}


def test_parent_account_context_does_not_rewrite_native_observation_and_expires():
    source = snapshot()
    job = {"state": "PD", "reason_or_nodelist": "AssocGrpJobsLimit", "slurm_account": "project-a"}
    before = deepcopy(job)
    value = restriction_for_job(job, normalize_snapshot(source, cluster="cluster-a"))
    assert value["account"] == "org-a" and value["code"] == "arrears"
    assert value["source"] == "sai_applied_policy" and job == before
    assert restriction_for_job(job, source, now=source["expires_at"]) is None
    for change in ({"state": "R"}, {"reason_or_nodelist": "Resources"}, {"slurm_account": "unmanaged"}):
        assert restriction_for_job({**job, **change}, source) is None
    del source["accounts"]["org-a"]["reason"]
    source["accounts"]["org-a"]["group_jobs_limit"] = None
    assert restriction_for_job(job, normalize_snapshot(source, cluster="cluster-a")) is None


def test_real_snapshot_read_rejects_wrong_cluster_shared_writes_and_symlinks(tmp_path):
    root = tmp_path / "observations"
    root.mkdir(mode=0o755)
    path = root / "cluster-a.json"
    path.write_text(json.dumps(snapshot()))
    path.chmod(0o644)
    options = {"cluster": "cluster-a", "root": root, "trusted_uids": (os.getuid(),)}
    assert read_snapshot(**options)["accounts"]["org-a"]["reason"] == "arrears"
    path.chmod(0o666)
    with pytest.raises(ValueError):
        read_snapshot(**options)
    path.chmod(0o644)
    bad = snapshot()
    bad["cluster_id"] = "cluster-b"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        read_snapshot(**options)
    path.unlink()
    target = root / "target.json"
    target.write_text(json.dumps(snapshot()))
    path.symlink_to(target)
    with pytest.raises(OSError):
        read_snapshot(**options)


@pytest.mark.parametrize("change", [
    {"group_jobs_limit": 2}, {"reason": "unverified"},
    {"lineage": ["root", "org-a", "org-a"]}, {"observed_at": True},
])
def test_malformed_account_context_is_not_published_as_a_verified_cause(change):
    value = snapshot()
    value["accounts"]["org-a"].update(change)
    with pytest.raises(ValueError):
        normalize_snapshot(value, cluster="cluster-a")
