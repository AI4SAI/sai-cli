"""Shared standard association metadata keeps operator notes and scoped job context."""
from copy import deepcopy
import pytest
from sai_compute_restrictions import (association_read_command, decode_association_comment,
    encode_association_comment, read_job_contexts, strip_association_comment)

OWNER = "11111111-2222-4333-8444-555555555555"


def encoded(note="", reason="arrears", revision=1, *, account="org-a", leaf="project-a", user="alice"):
    lineage = f"/{account}/{leaf}/0-{user}/"
    parents = []
    for ident, name in ((1, "root"), (3, account), (4, leaf)):
        owned = ident == 3
        parents.append({"account": name, "association_id": ident,
            "owner_ref": OWNER if owned else None, "revision": revision if owned else None,
            "reason": reason if owned else None, "limits": {},
            "numeric": {"group_jobs_limit": 0 if owned and reason else None,
                        "billing_tres_limit": None, "max_submit_jobs": None}})
    return encode_association_comment(note, account=account, association_id=3,
        owner_ref=OWNER, revision=revision, reason=reason, limits={}, ancestor_ids=[1, 3, 4],
        applied={"recorded_at": 100, "association_id": 47, "lineage": lineage, "parents": parents})


def test_reason_changes_and_open_preserve_original_note_exactly():
    note = "  MiXeD 'quoted' \"double\" \\ path / 中文\nlast line  "
    first = encoded(note)
    second = encoded(first, "admin_blocked", 2)
    cleared = encoded(second, None, 3)
    assert strip_association_comment(first) == strip_association_comment(second) == strip_association_comment(cleared) == note
    marker = decode_association_comment(second)
    assert second.startswith("[sai.account-state/v2:")
    assert {key: marker[key] for key in ("account", "association_id", "owner_ref", "revision", "reason")} == {
        "account": "org-a", "association_id": 3, "owner_ref": OWNER, "revision": 2, "reason": "admin_blocked"}
    assert encode_association_comment(second, **marker) == second
    assert decode_association_comment(cleared)["reason"] is None
    assert strip_association_comment("ordinary [brackets] note") == "ordinary [brackets] note"


def test_retired_prefix_is_rejected_and_encoder_requires_explicit_limits():
    old = f"[sai.account-state/v1:org-a:3:{OWNER}:1:arrears] manual note"
    for read in (decode_association_comment, strip_association_comment, encoded):
        with pytest.raises(ValueError):
            read(old)
    with pytest.raises(TypeError):
        encode_association_comment("note", account="org-a", association_id=3,
            owner_ref=OWNER, revision=1, reason="arrears")
    assert decode_association_comment("manual " + old) is None


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
        result = read_job_contexts([job, job, {**job, "state": "R"}], [47, 47, 99],
            cluster="cluster-a", fetch=fetch, now=123)
        expected = {} if reason is None else {"account_restriction": {
            "code": reason, "account": "org-a", "source": "sai_applied_policy", "observed_at": 123,
            "basis": "applied_record", "recorded_at": 100}}
        assert result == [expected, expected, {}]
    assert calls == [[47]] * 3 and job == before
    assert read_job_contexts([{**job, "reason_or_nodelist": "Resources"}], [47], cluster="cluster-a", fetch=fetch) == [{}]
    assert calls == [[47]] * 3
    assert association_read_command("cluster-a", [47])[-3:] == ["Cluster=cluster-a", "Ids=47", "WOPLimits"]


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
        read_job_contexts([job], [47], cluster="cluster-a", fetch=lambda ids: {"associations": [{**row, **change}]})


@pytest.mark.parametrize("value", [True, 0, -1, 2**32 - 2, "47"])
def test_invalid_association_id_cannot_change_native_query_scope(value):
    with pytest.raises(ValueError):
        association_read_command("cluster-a", [value])
