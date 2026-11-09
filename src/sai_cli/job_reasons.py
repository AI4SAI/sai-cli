"""Native waiting reasons and separately observed SAI account restrictions."""
from collections.abc import Mapping
from datetime import datetime, timezone
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
    "AssocMaxSubmitJobLimit": ("账户提交作业上限", "Account submitted-job limit"),
    "QOSGrpBilling": ("QOS并发资源上限", "QOS resource concurrency limit"),
}

_SERVICE_LEVEL_NAMES = {
    "personal_unverified": ("基础", "Basic"),
    "personal_standard": ("标准", "Standard"),
    "registration_trial": ("千卡尝鲜", "Registration trial"),
    "personal_advanced": ("高级", "Advanced"),
    "org_standard": ("标准", "Standard"),
    "standard": ("标准", "Standard"),
    "plus": ("Plus", "Plus"),
    "pro": ("Pro", "Pro"),
    "ultra": ("Ultra", "Ultra"),
}

_SOURCE_NAMES = {
    "service_level": ("服务等级", "Service level"),
    "grant": ("权益授予", "Grant"),
    "reservation": ("预留容量", "Reserved capacity"),
    "org_admin": ("组织设置", "Organization setting"),
    "project_pi": ("项目设置", "Project setting"),
    "hard_clamp": ("手动上限", "Manual cap"),
    "member_limit": ("成员设置", "Member setting"),
    "risk_control": ("风控限制", "Risk control"),
}

_GRANT_NAMES = {
    "baseline": ("基准授予", "Baseline grant"),
    "assurance": ("保障授予", "Assurance grant"),
    "contract": ("合同授予", "Contract grant"),
    "subscription": ("订阅授予", "Subscription grant"),
    "trial": ("试用授予", "Trial grant"),
    "mis": ("管理授予", "Management grant"),
}

_LIMIT_FIELDS = {"AssocGrpBilling": "billing_tres_limit", "AssocMaxSubmitJobLimit": "max_submit_jobs"}


def _limit_sources(sources: list[dict[str, Any]], *, chinese: bool) -> str:
    if not sources:
        return "来源未核实" if chinese else "Source unverified"
    entitlements, reservations, constraints = [], [], []
    for source in sources:
        kind = source["kind"]
        label = _SOURCE_NAMES[kind][0 if chinese else 1]
        if kind == "grant" and source.get("grant_kind"):
            label = _GRANT_NAMES[source["grant_kind"]][0 if chinese else 1]
        code = source.get("service_level_code")
        if code:
            label += " " + _SERVICE_LEVEL_NAMES.get(code, (code, code))[0 if chinese else 1]
        target = entitlements if kind in {"service_level", "grant"} else reservations if kind == "reservation" else constraints
        target.append(label)
    separator = "、" if chinese else ", "
    entitlement = separator.join(entitlements)
    if len(entitlements) > 1 and reservations:
        entitlement = f"({entitlement})"
    contributions = ([entitlement] if entitlement else []) + reservations
    return separator.join(([" + ".join(contributions)] if contributions else []) + constraints)


def _limit_lines(context: Mapping[str, Any], *, native: str, chinese: bool) -> list[str]:
    field = _LIMIT_FIELDS.get(native)
    lines = []
    if context.get("basis") == "applied_record":
        recorded = datetime.fromtimestamp(context["recorded_at"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(("账户限额记录" if chinese else "Account limit record") + " · " + recorded)
    for constraint in context["constraints"]:
        if constraint["field"] != field:
            continue
        scope = ("账户" if constraint["scope"] == "account" else "成员") if chinese else constraint["scope"].title()
        amount = (("并发额度 " if chinese else "Concurrency allowance ") + constraint["value"] + " billing"
                  if field == "billing_tres_limit" else ("提交作业数上限 " if chinese else "Submitted-job limit ") + constraint["value"])
        lines.append(f"{constraint['account']} {scope} · {amount} · "
                     + _limit_sources(constraint["sources"], chinese=chinese))
    return lines


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
            if restriction.get("basis") == "applied_record":
                recorded = datetime.fromtimestamp(restriction["recorded_at"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                label += "\n" + ("账户限制记录" if chinese else "Account restriction record") + " · " + recorded
        else:
            label += (" · 账户" if chinese else " · Account: ") + account_label
    if detail and job.get("limit_context") and native in _LIMIT_FIELDS:
        label = "\n".join([label, *_limit_lines(job["limit_context"], native=native, chinese=chinese)])
    return label
