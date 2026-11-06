"""Shared standard association metadata keeps operator notes and scoped job context."""
from copy import deepcopy
import pytest
from sai_compute_restrictions import (association_read_command, decode_association_comment,
    encode_association_comment, read_job_restrictions, strip_association_comment)

OWNER = "11111111-2222-4333-8444-555555555555"


def encoded(note="", reason="arrears", revision=1):
    return encode_association_comment(note, account="org-a", association_id=3,
        owner_ref=OWNER, revision=revision, reason=reason)


def test_reason_changes_and_open_preserve_original_note_exactly():
    note = "  MiXeD 'quoted' \"double\" \\ path / 中文\nlast line  "
    first = encoded(note)
    second = encoded(first, "admin_blocked", 2)
    cleared = encoded(second, None, 3)
    assert strip_association_comment(first) == strip_association_comment(second) == strip_association_comment(cleared) == note
    assert decode_association_comment(second) == {"account": "org-a", "association_id": 3,
        "owner_ref": OWNER, "revision": 2, "reason": "admin_blocked"}
    assert decode_association_comment(cleared)["reason"] is None
    assert strip_association_comment("ordinary [brackets] note") == "ordinary [brackets] note"


def test_visible_page_deduplicates_native_read_and_existing_job_sees_reason_change():
    job = {"state": "PD", "reason_or_nodelist": "AssocGrpJobsLimit", "slurm_account": "project-a",
           "slurm_user": "alice", "partition": "gpu"}
    before = deepcopy(job)
    row = {"id": 47, "cluster": "cluster-a", "account": "project-a", "user": "alice",
           "partition": "", "lineage": "/org-a/project-a/0-alice/", "comment": encoded("private operator note")}
    calls=[]
    def fetch(ids):
        calls.append(ids)
        return {"associations": [row], "errors": []}
    for reason, revision in (("arrears", 1), ("admin_blocked", 2), (None, 3)):
        row["comment"] = encoded(row["comment"], reason, revision)
        result = read_job_restrictions([job, job, {**job, "state": "R"}], [47, 47, 99],
            cluster="cluster-a", fetch=fetch, now=123)
        expected = None if reason is None else {"code": reason, "account": "org-a", "source": "sai_applied_policy", "observed_at": 123}
        assert result == [expected, expected, None]
    assert calls == [[47]] * 3 and job == before
    assert read_job_restrictions([{**job, "reason_or_nodelist": "Resources"}], [47], cluster="cluster-a", fetch=fetch) == [None]
    assert calls == [[47]] * 3
    assert association_read_command("cluster-a", [47])[-2:] == ["Cluster=cluster-a", "Ids=47"]


@pytest.mark.parametrize("change", [
    {"id": 48}, {"cluster": "cluster-b"}, {"user": "bob"}, {"account": "other"},
    {"partition": "cpu"}, {"lineage": "/unrelated/project-a/0-alice/"},
    {"comment": "[sai.account-state/v1:invalid]"},
])
def test_unrelated_or_malformed_association_never_enriches_a_job(change):
    job = {"state": "PD", "reason_or_nodelist": "AssocGrpJobsLimit", "slurm_account": "project-a",
           "slurm_user": "alice", "partition": "gpu"}
    row = {"id": 47, "cluster": "cluster-a", "account": "project-a", "user": "alice",
           "partition": "", "lineage": "/org-a/project-a/0-alice/", "comment": encoded()}
    with pytest.raises(ValueError):
        read_job_restrictions([job], [47], cluster="cluster-a", fetch=lambda ids: {"associations": [{**row, **change}]})


@pytest.mark.parametrize("value", [True, 0, -1, 2**32 - 2, "47"])
def test_invalid_association_id_cannot_change_native_query_scope(value):
    with pytest.raises(ValueError):
        association_read_command("cluster-a", [value])
