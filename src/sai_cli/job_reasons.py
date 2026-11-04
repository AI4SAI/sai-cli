"""Short presentation of the scheduler's validated pending reason."""
from collections.abc import Mapping
from typing import Any


_LABELS = {
    "arrears": ("欠费", "Arrears"),
    "severe_arrears": ("严重欠费", "Severe arrears"),
    "no_compute_funding": ("资金不足", "Insufficient funds"),
    "admin_blocked": ("管理停用", "Administratively disabled"),
}


def job_reason(job: Mapping[str, Any], *, language: str = "zh-CN", detail: bool = False) -> str | None:
    native = job.get("reason_or_nodelist")
    reason = job.get("pending_reason")
    if job.get("state") != "PD" or native != "AssocGrpJobsLimit" or not reason:
        return native
    labels = _LABELS.get(reason["code"])
    if labels is None:
        return native
    chinese = language == "zh-CN"
    label = labels[0 if chinese else 1]
    if detail:
        label += (" · 阻塞账户 " if chinese else " · Blocking account ") + reason["account"]
    return label
