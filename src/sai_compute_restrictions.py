"""Standard Slurm association metadata shared by SAI writers and readers."""
from __future__ import annotations

import re
import time
from typing import Any

REASONS = frozenset({"arrears", "severe_arrears", "no_compute_funding", "admin_blocked"})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}")


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


_PREFIX = "[sai.account-state/v1:"
_MARKER = re.compile(
    r"\[sai\.account-state/v1:([A-Za-z0-9][A-Za-z0-9_.+\-]{0,127}):"
    r"([1-9][0-9]{0,9}):([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}):"
    r"([1-9][0-9]{0,18}):(open|arrears|severe_arrears|no_compute_funding|admin_blocked)\]"
)
ASSOCIATION_BATCH_SIZE = 512


def decode_association_comment(comment: object) -> dict[str, Any] | None:
    """Decode only our ASCII prefix; native cache escaping of notes is irrelevant."""
    if comment is None or comment == "":
        return None
    if not isinstance(comment, str) or len(comment.encode("utf-8")) > 65536:
        raise ValueError("invalid association comment")
    if not comment.startswith(_PREFIX):
        return None
    match = _MARKER.match(comment)
    if match is None or (match.end() < len(comment) and comment[match.end()] != " "):
        raise ValueError("invalid managed association prefix")
    account, association_id, owner_ref, revision, reason = match.groups()
    association_id, revision = int(association_id), int(revision)
    if association_id >= 2**32 - 2 or revision > 2**63 - 1:
        raise ValueError("invalid managed association generation")
    return {"account": account, "association_id": association_id, "owner_ref": owner_ref,
            "revision": revision, "reason": None if reason == "open" else reason}


def strip_association_comment(comment: str | None) -> str:
    """Preserve the original database note, including its spaces and quotes."""
    if comment is None:
        return ""
    if decode_association_comment(comment) is None:
        return comment
    end = _MARKER.match(comment).end()
    return comment[end + 1:] if end < len(comment) else ""


def encode_association_comment(comment: str | None, *, account: str, association_id: int,
                               owner_ref: str, revision: int, reason: str | None) -> str:
    account = _name(account)
    validate_reason(reason)
    if type(association_id) is not int or type(revision) is not int:
        raise ValueError("invalid managed association generation")
    prefix = f"{_PREFIX}{account}:{association_id}:{owner_ref}:{revision}:{reason or 'open'}]"
    decode_association_comment(prefix)
    note = strip_association_comment(comment)
    value = prefix + (" " + note if note else "")
    if len(value.encode("utf-8")) > 65536:
        raise ValueError("association comment exceeds native input bound")
    return value


def association_read_command(cluster: str, ids: list[int]) -> list[str]:
    _name(cluster)
    if (not ids or len(ids) > ASSOCIATION_BATCH_SIZE
            or any(type(value) is not int or not 0 < value < 2**32 - 2 for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("invalid association query cohort")
    return ["sacctmgr", "--json", "show", "association", "where", f"Cluster={cluster}",
            "Ids=" + ",".join(str(value) for value in ids)]


def read_job_restrictions(jobs: list[dict[str, Any]], association_ids: list[object], *,
                          cluster: str, fetch, now: float | None = None) -> list[dict[str, Any] | None]:
    """Batch current native metadata only for the already visible queue page."""
    _name(cluster)
    if len(jobs) != len(association_ids):
        raise ValueError("job association bindings are incomplete")
    eligible = [i for i, job in enumerate(jobs)
                if job.get("state") in {"PD", "PENDING"}
                and job.get("reason_or_nodelist") == "AssocGrpJobsLimit"]
    ids, seen = [], set()
    for index in eligible:
        value = association_ids[index]
        if value is None:
            continue
        if type(value) is not int or not 0 < value < 2**32 - 2:
            raise ValueError("invalid native job association")
        if value not in seen:
            ids.append(value)
            seen.add(value)
    rows = {}
    for offset in range(0, len(ids), ASSOCIATION_BATCH_SIZE):
        cohort = ids[offset:offset + ASSOCIATION_BATCH_SIZE]
        payload = fetch(cohort)
        if (not isinstance(payload, dict) or payload.get("errors")
                or not isinstance(payload.get("associations"), list)
                or len(payload["associations"]) > len(cohort)):
            raise ValueError("invalid native association result")
        for row in payload["associations"]:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or row["id"] not in cohort or row["id"] in rows or row.get("cluster") != cluster):
                raise ValueError("native association returned outside the requested cohort")
            rows[row["id"]] = row
    results = [None] * len(jobs)
    observed = int(time.time() if now is None else now)
    for index in eligible:
        row = rows.get(association_ids[index])
        if row is None:
            continue
        job = jobs[index]
        if row.get("account") != job.get("slurm_account") or row.get("user") != job.get("slurm_user"):
            raise ValueError("native association does not match the observed job")
        partition = row.get("partition") or ""
        if not isinstance(partition, str) or (partition and partition not in (job.get("partition") or "").split(",")):
            raise ValueError("native association partition does not match the observed job")
        marker = decode_association_comment(row.get("comment"))
        if marker is None or marker["reason"] is None:
            continue
        lineage = row.get("lineage")
        if (not isinstance(lineage, str) or not lineage.startswith("/") or not lineage.endswith("/")
                or (marker["account"] != "root" and marker["account"] not in lineage.split("/")[1:-1])):
            raise ValueError("account context is outside the observed association lineage")
        results[index] = {"code": marker["reason"], "account": marker["account"],
                          "source": "sai_applied_policy", "observed_at": observed}
    return results


def validate_account_restriction(value: object, *, state: object, reason: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if (not isinstance(value, dict) or not isinstance(state, str) or state not in {"PD", "PENDING"}
            or reason != "AssocGrpJobsLimit" or value.get("source") != "sai_applied_policy"
            or not isinstance(value.get("code"), str) or value["code"] not in REASONS):
        raise ValueError("invalid SAI account restriction")
    return {"code": value["code"], "account": _name(value.get("account")),
            "source": "sai_applied_policy", "observed_at": _time(value.get("observed_at"))}
