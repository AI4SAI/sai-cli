"""Deterministic JSON and plain-text table output."""

from __future__ import annotations

import json
from typing import Any, Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from .catalog import ResourceCatalog
from .contracts import AccountStatus, JobItem, JobResult, RunningEstimateItem, RunningEstimateResult
from .site_jobs import SiteJobResult


_COLUMNS = (
    ("job_id", "Job-ID", 18),
    ("priority", "Prior", 10),
    ("name", "Name", 24),
    ("slurm_user", "User", 16),
    ("submit_or_start", "Submit/Start at", 25),
    ("state", "ST", 10),
    ("run_wait", "Run/Wait", 14),
    ("partition", "Partition", 18),
    ("qos", "QOS", 18),
    ("nodes", "Nodes", 8),
    ("slots", "Slots", 8),
    ("gpus_per_node", "GPU", 8),
    ("mem_per_unit", "MemPerU", 12),
    ("array_task_id", "array_ID", 12),
    ("reason_or_nodelist", "Reason/Nodelist", 36),
)

_RUNNING_ESTIMATE_COLUMNS = (
    ("job_id", "Job-ID", 20),
    ("state", "State", 14),
    ("elapsed", "Elapsed", 14),
    ("billable", "Billable", 18),
    ("usage", "Usage", 18),
    ("gross", "Gross est. CNY", 16),
    ("estimate", "Estimate", 16),
    ("uncertainty", "Uncertainty", 36),
)


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_account_status(status: AccountStatus) -> str:
    lines = ["身份认证：" + ("当前有效" if status.verification_current else "当前无有效认证")]
    if status.initial_verification_deadline and not status.verification_current:
        deadline = datetime.fromisoformat(status.initial_verification_deadline.replace("Z", "+00:00"))
        lines.append(f"首次认证截止：{deadline.astimezone().isoformat(timespec='seconds')}（365 天宽限）")
        lines.append("请在截止前完成认证，逾期将暂停新的集群登录和作业提交。")
    messages = {
        "restriction_pending": "正在暂停新的集群登录和作业提交，现有会话及运行中的作业不受影响。",
        "restricted": "新的集群登录和作业提交已暂停。",
        "recovery_pending": "正在等待站点恢复登录和作业提交。",
        "failed": "登录和作业提交状态未能更新，请联系 SAI 运营团队，无需重复认证。",
    }
    if status.access_state in messages:
        lines.append(messages[status.access_state])
    lines.append(f"认证入口：{status.verification_url}")
    return "\n".join(lines) + "\n"


def _duration(seconds: object) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        return "-"
    sign = "-" if seconds < 0 else ""
    remaining = abs(seconds)
    days, remaining = divmod(remaining, 86_400)
    hours, remaining = divmod(remaining, 3_600)
    minutes, secs = divmod(remaining, 60)
    prefix = f"{days}-" if days else ""
    return f"{sign}{prefix}{hours:02d}:{minutes:02d}:{secs:02d}"


def _display(value: object) -> str:
    if value is None or value == "":
        return "-"
    return "".join(
        character if ord(character) >= 32 and ord(character) != 127 else "?"
        for character in str(value)
    )


def _site_time(value: str, *, timezone_name: str) -> str:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return instant.astimezone(ZoneInfo(timezone_name)).isoformat(timespec="seconds")


def _row(item: JobItem) -> dict[str, str]:
    values = item.values
    return {
        "job_id": _display(values["job_id"]),
        "priority": _display(values["priority"]),
        "name": _display(values["name"]),
        "slurm_user": _display(values["slurm_user"]),
        "submit_or_start": _display(values["start_time"] or values["submit_time"]),
        "state": _display(values["state"]),
        "run_wait": _duration(values["run_wait_seconds"]),
        "partition": _display(values["partition"]),
        "qos": _display(values["qos"]),
        "nodes": _display(values["nodes"]),
        "slots": _display(values["slots"]),
        "gpus_per_node": _display(values["gpus_per_node"]),
        "mem_per_unit": _display(values["mem_per_unit"]),
        "array_task_id": _display(values["array_task_id"]),
        "reason_or_nodelist": _display(values["reason_or_nodelist"]),
    }


def _estimate_state(item: RunningEstimateItem) -> str:
    status = item.values["estimate_status"]
    if status == "not_started":
        return "PENDING"
    if status == "unavailable":
        return "UNAVAILABLE"
    return str(status).upper()


def _billable(item: RunningEstimateItem) -> str:
    resources = item.values["resources"]
    resource_type = resources["resource_type"]
    resource_count = resources["resource_count"]
    if resource_type is None or resource_count is None:
        return "-"
    return f"{resource_count} {resource_type}"


def _running_estimate_row(item: RunningEstimateItem) -> dict[str, str]:
    values = item.values
    return {
        "job_id": _display(values["job_id_raw"] or values["job_key"]),
        "state": _display(values["state"]),
        "elapsed": _duration(values["elapsed_seconds"]),
        "billable": _billable(item),
        "usage": _display(values["resources"]["usage_quantity"]),
        "gross": _display(values["gross_cny"]),
        "estimate": _estimate_state(item),
        "uncertainty": _display(",".join(values["uncertainty"])),
    }


def _truncate(text: str, maximum: int) -> str:
    if len(text) <= maximum:
        return text
    if maximum <= 3:
        return text[:maximum]
    return f"{text[:maximum - 3]}..."


def _line(values: Iterable[str], widths: list[int]) -> str:
    cells = [value.ljust(width) for value, width in zip(values, widths, strict=True)]
    return "  ".join(cells).rstrip()


def render_resource_catalog(result: ResourceCatalog) -> str:
    catalog = result.as_dict()

    def cell(value: object) -> str:
        return "unknown" if value is None else _truncate(" ".join(str(value).split()), 60)

    def table(headings: list[str], rows: list[list[object]]) -> list[str]:
        rendered = [[cell(value) for value in row] for row in rows]
        widths = [max(len(heading), *(len(row[index]) for row in rendered))
                  for index, heading in enumerate(headings)] if rendered else [len(h) for h in headings]
        return [_line(headings, widths), *(_line(row, widths) for row in rendered)] if rendered else ["(none published)"]

    lines = [f"Site: {cell(catalog['site_label'])} ({cell(catalog['site_id'])})", "Compute"]
    lines.extend(table(
        ["Partition", "Kind", "Nodes", "CPU/node", "GPUs(total)", "GPU model", "Published price"],
        [[row["name"], row["resource_kind"], row["node_count"], row["cpu_cores_per_node"],
          row["gpu_count"], row["gpu_model"], row["pricing"]["display"] if row["pricing"] else None]
         for row in catalog["compute"]],
    ))
    lines.extend(("", "Storage"))
    lines.extend(table(
        ["Name", "Scope", "Filesystem", "Package price", "Usage price", "Metered"],
        [[row["name"], row["scope_label"], row["filesystem_type"], row["package_pricing"]["display"],
          row["usage_pricing"]["display"], "yes" if row["metered_settlement_enabled"] else "no"]
         for row in catalog["storage"]],
    ))
    lines.append("Published specifications and prices; availability, access and final charges are separate.")
    return "\n".join(lines) + "\n"


def _job_table_lines(items: tuple[JobItem, ...]) -> list[str]:
    rows = [_row(item) for item in items]
    widths: list[int] = []
    for key, heading, maximum in _COLUMNS:
        widest = max([len(heading), *(len(row[key]) for row in rows)], default=len(heading))
        widths.append(min(widest, maximum))

    lines = [
        _line((heading for _, heading, _ in _COLUMNS), widths),
        _line(("-" * width for width in widths), widths),
    ]
    if rows:
        for row in rows:
            lines.append(
                _line(
                    (_truncate(row[key], maximum) for key, _, maximum in _COLUMNS),
                    widths,
                )
            )
    else:
        lines.append("(no jobs)")
    lines.extend(
        (
            "GPU is the GPU count per node.",
            "MemPerU is host memory per GPU or CPU logical unit.",
            "Slots may represent requested tasks while pending and allocated CPU slots while running.",
        )
    )
    return lines


def render_table(result: JobResult) -> str:
    header = (
        f"Site: {result.site_id}  Cluster: {result.cluster_id}  "
        f"Scope: {result.scope}  Source: {result.freshness.source}  "
        f"Queried: {result.freshness.queried_at}"
    )
    return "\n".join([header, *_job_table_lines(result.items)]) + "\n"


def render_site_jobs(result: SiteJobResult) -> str:
    freshness = result.freshness
    lines = [
        f"Site: {result.site_id}  Cluster: {result.cluster_id}  "
        f"Scope: {result.scope_type}  Source: {freshness.source}",
        f"Observed: {freshness.observed_at}  Age: {freshness.age_seconds}s  "
        f"Stale: {'yes' if freshness.stale else 'no'}  Has-more: {'yes' if result.has_more else 'no'}",
        *_job_table_lines(result.items),
    ]
    return "\n".join(lines) + "\n"


def render_running_estimate_table(result: RunningEstimateResult) -> str:
    rows = [_running_estimate_row(item) for item in result.items]
    widths: list[int] = []
    for key, heading, maximum in _RUNNING_ESTIMATE_COLUMNS:
        widest = max([len(heading), *(len(row[key]) for row in rows)], default=len(heading))
        widths.append(min(widest, maximum))

    stale = "yes" if result.freshness.stale else "no"
    lines = [
        (
            f"Site: {result.site_id}  Cluster: {result.cluster_id}  Scope: {result.scope}  "
            f"Timezone: {result.site_timezone}  "
            f"As-of: {_site_time(result.as_of, timezone_name=result.site_timezone)}  Final: false"
        ),
        (
            f"Observed: {_site_time(result.freshness.observed_at, timezone_name=result.site_timezone)}  "
            f"Age: {result.freshness.age_seconds}s  "
            f"Stale: {stale}  Source: {result.freshness.source}  ETag: {result.etag}"
        ),
        _line((heading for _, heading, _ in _RUNNING_ESTIMATE_COLUMNS), widths),
        _line(("-" * width for width in widths), widths),
    ]
    if rows:
        for row in rows:
            lines.append(
                _line(
                    (
                        _truncate(row[key], maximum)
                        for key, _, maximum in _RUNNING_ESTIMATE_COLUMNS
                    ),
                    widths,
                )
            )
    else:
        lines.append("(no running jobs)")
    lines.append("Gross amounts are running estimates only; final charges may differ.")
    return "\n".join(lines) + "\n"
