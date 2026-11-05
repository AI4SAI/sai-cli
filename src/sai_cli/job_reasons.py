"""Native waiting reasons and separately observed SAI account restrictions."""
from collections.abc import Mapping
from typing import Any


_LABELS = {
    "arrears": ("欠费", "Arrears"),
    "severe_arrears": ("严重欠费", "Severe arrears"),
    "no_compute_funding": ("资金不足", "Insufficient funds"),
    "admin_blocked": ("管理停用", "Administratively disabled"),
}

_NATIVE_LABELS = {
    "JobHeldUser": ("用户挂起", "Held by user"),
    "JobHeldAdmin": ("管理员挂起", "Held by administrator"),
    "JobArrayTaskLimit": ("数组并发上限", "Array concurrency limit"),
    "Dependency": ("等待依赖", "Waiting for dependency"),
    "DependencyNeverSatisfied": ("依赖无法满足", "Unsatisfiable dependency"),
    "BeginTime": ("未到开始时间", "Waiting for start time"),
    "Priority": ("等待优先调度", "Waiting for priority"),
    "Resources": ("等待资源", "Waiting for resources"),
    "AssocGrpJobsLimit": ("账户并发上限", "Account concurrency limit"),
    "AssocMaxJobsLimit": ("账户内个人并发上限", "Per-user concurrency limit in account"),
    "QOSGrpJobsLimit": ("QOS 并发上限", "QOS concurrency limit"),
    "QOSMaxJobsPerUserLimit": ("QOS 用户并发上限", "QOS per-user concurrency limit"),
    "MaxJobsPerAccount": ("QOS 账户并发上限", "QOS per-account concurrency limit"),
    "AssocGrpCpuLimit": ("账户 CPU 上限", "Account CPU limit"),
    "AssocGrpMemLimit": ("账户内存上限", "Account memory limit"),
    "AssocGrpNodeLimit": ("账户节点上限", "Account node limit"),
    "AssocGrpGRES": ("账户通用资源上限", "Account generic resource limit"),
    "QOSGrpCpuLimit": ("QOS CPU 上限", "QOS CPU limit"),
    "QOSGrpMemLimit": ("QOS 内存上限", "QOS memory limit"),
    "QOSGrpNodeLimit": ("QOS 节点上限", "QOS node limit"),
    "QOSGrpGRES": ("QOS 通用资源上限", "QOS generic resource limit"),
    "AssocMaxCpuPerJobLimit": ("账户单作业 CPU 上限", "Account per-job CPU limit"),
    "AssocMaxMemPerJob": ("账户单作业内存上限", "Account per-job memory limit"),
    "AssocMaxNodePerJobLimit": ("账户单作业节点上限", "Account per-job node limit"),
    "AssocMaxGRESPerJob": ("账户单作业通用资源上限", "Account per-job generic resource limit"),
    "QOSMaxCpuPerJobLimit": ("QOS 单作业 CPU 上限", "QOS per-job CPU limit"),
    "QOSMaxMemoryPerJob": ("QOS 单作业内存上限", "QOS per-job memory limit"),
    "QOSMaxNodePerJobLimit": ("QOS 单作业节点上限", "QOS per-job node limit"),
    "QOSMaxGRESPerJob": ("QOS 单作业通用资源上限", "QOS per-job generic resource limit"),
    "AssocGrpBilling": ("账户并发资源上限", "Account resource concurrency limit"),
    "QOSGrpBilling": ("QOS并发资源上限", "QOS resource concurrency limit"),
}


def job_reason(job: Mapping[str, Any], *, language: str = "zh-CN", detail: bool = False) -> str | None:
    native = job.get("reason_or_nodelist")
    restriction = job.get("account_restriction")
    if job.get("state") != "PD":
        return native
    labels = _NATIVE_LABELS.get(native)
    if labels is None:
        return native
    chinese = language == "zh-CN"
    label = labels[0 if chinese else 1]
    if detail:
        label += f" ({native})"
    if native == "AssocGrpJobsLimit" and restriction and restriction["source"] == "sai_applied_policy":
        account_label = _LABELS[restriction["code"]][0 if chinese else 1]
        if detail:
            label += ("\nSAI 账户限制：" if chinese else "\nSAI account restriction: ") + account_label + " · " + restriction["account"]
        else:
            label += (" · 账户" if chinese else " · Account: ") + account_label
    return label
