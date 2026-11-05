"""The same native cause is written by the site and read by all consumers."""
import pytest

from sai_native_slurm import (
    COMPUTE_BLOCK_REASONS, normalize_job_pending_reason,
    read_compute_gate_comment, write_compute_gate_comment,
)


def test_reason_changes_and_recovery_preserve_operator_comment():
    note = "Operations | 调整说明\nsecond line  "
    for reason in COMPUTE_BLOCK_REASONS:
        published = write_compute_gate_comment(note, reason)
        assert read_compute_gate_comment(published) == reason
        updated = write_compute_gate_comment(published, "admin_blocked")
        assert read_compute_gate_comment(updated) == "admin_blocked"
        assert write_compute_gate_comment(updated, None) == note
        assert write_compute_gate_comment(updated, "admin_blocked") == updated
    assert write_compute_gate_comment(None, None) == ""
    assert read_compute_gate_comment(note) is None
    with pytest.raises(ValueError):
        write_compute_gate_comment("[sai.compute-gate/v1:unrecognized] keep", "arrears")
    with pytest.raises(ValueError):
        write_compute_gate_comment(note, "unrecognized")


def test_only_actual_native_account_blocker_produces_a_public_reason():
    raw = {"job_state": ["PENDING"], "state_reason": "AssocGrpJobsLimit",
           "state_description": "Arrears: research"}
    assert normalize_job_pending_reason(raw) == {"code": "arrears", "account": "research"}
    for change in (
        {"job_state": ["RUNNING"]}, {"state_reason": "Resources"},
        {"state_reason": "JobHeldUser"}, {"job_state": {}},
        {"state_description": "[sai.compute-gate/v1:unknown] account=research"},
        {"state_description": raw["state_description"] + " private note"},
        {"state_description": raw["state_description"] + "\x1b[31m"},
        {"state_description": None, "comment": raw["state_description"]},
    ):
        assert normalize_job_pending_reason({**raw, **change}) is None
