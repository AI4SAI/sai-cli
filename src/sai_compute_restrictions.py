"""Read SAI account-policy observations independently of upstream Slurm."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any

SCHEMA = "sai.compute-restrictions/v1"
DEFAULT_ROOT = "/opt/sai/runtime/admission"
REASONS = frozenset({"arrears", "severe_arrears", "no_compute_funding", "admin_blocked"})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}")
_MAX_BYTES = 4 * 1024 * 1024


def validate_reason(value: object) -> str | None:
    if value is not None and (not isinstance(value, str) or value not in REASONS):
        raise ValueError("invalid SAI account restriction")
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError("invalid native account or cluster")
    return value


def _time(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 253402300799:
        raise ValueError("invalid observation time")
    return value


def normalize_snapshot(value: object, *, cluster: str) -> dict[str, Any]:
    cluster = _name(cluster)
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA
            or value.get("cluster_id") != cluster or not isinstance(value.get("accounts"), dict)
            or len(value["accounts"]) > 8192):
        raise ValueError("invalid SAI account-policy snapshot")
    accounts = {}
    for account, row in value["accounts"].items():
        account = _name(account)
        if not isinstance(row, dict):
            raise ValueError("invalid account-policy observation")
        lineage = row.get("lineage")
        if (not isinstance(lineage, list) or not 1 <= len(lineage) <= 64
                or any(not isinstance(name, str) or _NAME.fullmatch(name) is None for name in lineage)
                or len(set(lineage)) != len(lineage) or lineage[-1] != account):
            raise ValueError("invalid native account lineage")
        group_jobs = row.get("group_jobs_limit")
        if group_jobs is not None and (type(group_jobs) is not int or not 0 <= group_jobs <= 2**31 - 1):
            raise ValueError("invalid native group job limit")
        normalized = {"lineage": list(lineage), "group_jobs_limit": group_jobs,
                      "observed_at": _time(row.get("observed_at"))}
        reason = row.get("reason")
        if reason is not None:
            if not isinstance(reason, str) or reason not in REASONS or group_jobs != 0:
                raise ValueError("account reason requires its observed closed gate")
            normalized["reason"] = reason
        accounts[account] = normalized
    published = _time(value.get("published_at"))
    expires = _time(value.get("expires_at"))
    generation = value.get("generation")
    if (type(generation) is not int or not 0 <= generation <= 2**63 - 1
            or expires != published + 300
            or any(row["observed_at"] > published for row in accounts.values())):
        raise ValueError("invalid account-policy publication")
    return {"schema_version": SCHEMA, "cluster_id": cluster, "generation": generation,
            "published_at": published, "expires_at": expires, "accounts": accounts}


def read_snapshot(*, cluster: str, root: str | Path = DEFAULT_ROOT,
                  trusted_uids: tuple[int, ...] = (0,)) -> dict[str, Any] | None:
    """A missing optional observation never prevents the native queue read."""
    root = Path(root)
    path = root / (_name(cluster) + ".json")
    try:
        parent = root.parent.lstat()
        directory = root.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid not in trusted_uids or parent.st_mode & 0o022
                or not stat.S_ISDIR(directory.st_mode)
                or directory.st_mode & 0o022):
            raise ValueError("unsafe account-policy directory")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != directory.st_uid
                or info.st_mode & 0o022 or info.st_size > _MAX_BYTES):
            raise ValueError("unsafe account-policy snapshot")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES or os.fstat(fd).st_size != info.st_size:
            raise ValueError("account-policy snapshot changed during read")
    finally:
        os.close(fd)
    return normalize_snapshot(json.loads(raw), cluster=cluster)


def restriction_for_job(job: dict[str, Any], snapshot: dict[str, Any] | None, *,
                        now: float | None = None) -> dict[str, Any] | None:
    """Attach account context, without claiming Slurm selected this business cause."""
    observed_now = time.time() if now is None else now
    if (snapshot is None or not snapshot["published_at"] <= observed_now < snapshot["expires_at"]
            or job.get("state") != "PD"
            or job.get("reason_or_nodelist") != "AssocGrpJobsLimit"):
        return None
    account = job.get("slurm_account")
    row = snapshot["accounts"].get(account)
    if row is None:
        return None
    for ancestor in reversed(row["lineage"]):
        policy = snapshot["accounts"].get(ancestor)
        if policy is not None and policy.get("reason") is not None:
            return {"code": policy["reason"], "account": ancestor,
                    "source": "sai_applied_policy", "observed_at": policy["observed_at"]}
    return None


def validate_account_restriction(value: object, *, state: object, reason: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if (not isinstance(value, dict) or not isinstance(state, str) or state not in {"PD", "PENDING"}
            or reason != "AssocGrpJobsLimit" or value.get("source") != "sai_applied_policy"
            or not isinstance(value.get("code"), str) or value["code"] not in REASONS):
        raise ValueError("invalid SAI account restriction")
    return {"code": value["code"], "account": _name(value.get("account")),
            "source": "sai_applied_policy", "observed_at": _time(value.get("observed_at"))}
