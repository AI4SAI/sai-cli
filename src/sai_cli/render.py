"""Deterministic JSON and plain-text table output."""

from __future__ import annotations

import json
from typing import Any, Iterable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from textwrap import fill
from zoneinfo import ZoneInfo

from .catalog import ResourceCatalog
from .contracts import AccountStatus, JobCostResult, JobItem, JobResult, RunningEstimateItem, RunningEstimateResult
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary
from .native_quota import NativeQuotaResult


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
    ("job_id", "Job"),
    ("state", "State"),
    ("gross", "Standard"),
    ("cash", "Cash before Credit"),
)


def format_decimal(value: str, places: int = 2, *, trim: bool = False) -> str:
    """Format a validated decimal for readers without hiding nonzero small values."""
    amount = Decimal(value)
    if amount.is_zero():
        amount = Decimal(0)
    with localcontext() as context:
        context.rounding = ROUND_HALF_UP
        if 0 < amount.copy_abs() < Decimal(1).scaleb(-places):
            return f"{amount:,f}".rstrip("0").rstrip(".")
        text = f"{amount:,.{places}f}"
    return text.rstrip("0").rstrip(".") if trim and "." in text else text


def render_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    # JSON already escapes C0; escape the remaining terminal control range too.
    return encoded.translate({value: f"\\u{value:04x}" for value in range(127, 160)}) + "\n"


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


def _running_estimate_row(item: RunningEstimateItem) -> dict[str, str]:
    values = item.values
    missing = "Not started" if values["estimate_status"] == "not_started" else "Unavailable"
    return {
        "job_id": values["job_id_raw"] or values["job_key"] or "Unknown job",
        "state": values["state"] or "Unknown",
        "gross": format_decimal(values["gross_cny"]) if values["gross_cny"] is not None else missing,
        "cash": (format_decimal(values["cash_before_credit_cny"]) if values["cash_before_credit_cny"] is not None
                 else "Restricted" if "cash_price_restricted" in values["uncertainty"] else missing),
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


def render_storage_quota_summary(result: StorageQuotaSummary) -> str:
    values = result.values
    lines = [
        f"Workspace: {_display(values['workspace_key'])}  Site: {_display(values['site_id'])}",
        f"State: {_display(values['state'])}  Source: {_display(values['source'])}",
        f"Target total TiB: {_display(values['target_total_tib'])}",
        f"Effective total TiB: {_display(values['effective_total_tib'])}",
        f"Used TiB: {_display(values['used_tib'])}  Remaining TiB: {_display(values['remaining_tib'])}",
        f"Observed soft/hard TiB: {_display(values['observed_soft_limit_tib'])}/{_display(values['observed_hard_limit_tib'])}",
        f"Used inodes: {_display(values['used_inodes'])}  Inode soft/hard: {_display(values['inode_soft_limit'])}/{_display(values['inode_hard_limit'])}",
        f"Observed at: {_display(values['observed_at'])}  Quota updated: {_display(values['quota_updated_at'])}",
        "Stored observation; check its time. No live filesystem query or final charge.",
    ]
    return "\n".join(lines) + "\n"


def render_native_quota(result: NativeQuotaResult) -> str:
    values = result.values
    lines = [
        f"Workspace: {_display(values['workspace_key'])}  Site: {_display(values['site_id'])}",
        f"Source: lustre_quota  Query completed: {_display(values['as_of'])}",
        "Authorized quota subjects; these rows are not an organization pool total.",
        "Native limits use 0 for unlimited. Counters are exact bytes and inodes.",
    ]
    for row in values["items"]:
        lines.extend([
            "", f"{_display(row['label'])} ({_display(row['kind'])})",
            f"Quota: {_display(row['quota_ref'])}  Observed: {_display(row['observed_at'])}",
            f"Used bytes: {row['used_bytes']}  Soft/hard bytes: {row['block_soft_bytes']}/{row['block_hard_bytes']}",
            f"Used inodes: {row['used_inodes']}  Soft/hard inodes: {row['inode_soft']}/{row['inode_hard']}",
        ])
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


def render_site_allocation(result: SiteJobAllocationResult) -> str:
    freshness = result.freshness
    lines = [
        f"Site: {result.site_id}  Cluster: {result.cluster_id}  Scope: {result.scope_type}",
        f"Source: {freshness.source}  Observed: {freshness.observed_at}  "
        f"Age: {freshness.age_seconds}s  Stale: {'yes' if freshness.stale else 'no'}",
        f"Job: {_display(result.job.values['job_id'])}  "
        f"Array task: {_display(result.job.values['array_task_id'])}  "
        f"Scheduler states: {', '.join(result.scheduler_states)}",
        f"Restart count: {_display(result.restart_count)}  Allocation: {result.allocation_status}",
    ]
    if result.nodes:
        rows = [(node.name, str(node.cpus), _display(node.memory_mib),
                 "Unknown" if node.gres is None else "; ".join(
                     f"{item.name}{':' + item.type if item.type is not None else ''}: {item.count}"
                     f" (Slurm indices: {'Unknown' if item.indices is None else format_allocation_indices(item.indices)})"
                     for item in node.gres)) for node in result.nodes]
        headings = ("Node", "Allocated CPUs", "Allocated memory (MiB)", "Allocated GRES (Slurm units)")
        widths = [max(len(heading), *(len(row[index]) for row in rows))
                  for index, heading in enumerate(headings)]
        lines.extend((_line(headings, widths), _line(("-" * width for width in widths), widths)))
        lines.extend(_line(row, widths) for row in rows)
        lines.append("Slurm resource units and indices do not identify CUDA/NVML devices, physical slots or MIG parents.")
    return "\n".join(lines) + "\n"


def format_allocation_indices(indices: tuple[int, ...]) -> str:
    """Keep every scheduler index while compressing adjacent ranges for display."""
    ranges: list[str] = []
    start = end = indices[0]
    for index in indices[1:]:
        if index == end + 1:
            end = index
            continue
        ranges.append(str(start) if start == end else f"{start}-{end}")
        start = end = index
    ranges.append(str(start) if start == end else f"{start}-{end}")
    return ", ".join(ranges)


def render_site_placement(result: SiteJobPlacementResult) -> str:
    lines = [render_site_allocation(result.allocation).rstrip(), "Recorded locations (operator records)"]
    if result.inventory is not None:
        lines.append(f"Published: {result.inventory.published_at}  Valid until: {result.inventory.expires_at}")
    for node in result.nodes:
        registration = node.registration
        if registration is None:
            lines.append(f"{node.name}: {'Record expired' if node.status == 'expired' else 'Not registered'}")
            continue
        rack = registration.rack
        location = "Location unknown" if rack is None else f"{rack.label}, U{rack.u_start}, height {rack.u_height}U"
        lines.extend((f"{node.name}: {registration.label} · {location}",
                      f"  Verified: {registration.verified_at}  Valid until: {registration.valid_until}"))
    lines.append("These are operator records for allocated nodes; they do not attest the current machine instance.")
    return "\n".join(lines) + "\n"


def render_running_estimate_table(result: RunningEstimateResult | JobCostResult, *, width: int = 80) -> str:
    """Show price facts without clipping money or treating missing estimates as zero."""
    if isinstance(result, JobCostResult):
        context, items = result.observation, (result.estimate,)
        # Job-detail timestamps are UTC; this contract has no site timezone.
        timezone_name, title = "UTC", "Job estimate"
    else:
        context, items = result, result.items
        timezone_name, title = result.site_timezone, "Running estimates"
    width = max(20, width)
    rows = [_running_estimate_row(item) for item in items]
    widths = [max(len(heading), *(len(row[key]) for row in rows)) if rows else len(heading)
              for key, heading in _RUNNING_ESTIMATE_COLUMNS]
    tabular = sum(widths) + 2 * (len(widths) - 1) <= width
    scope = context.scope.replace("_", " ")
    subject = context.slurm_user if context.scope == "self" else context.slurm_account
    context_line = (f"Slurm Account: {result.estimate.values['slurm_account'] or 'Unknown'}"
                    if isinstance(result, JobCostResult) else f"For: {subject or 'Unknown'} ({scope})")
    lines = [f"{title} (CNY; not settled)",
             fill(f"Site: {context.site_id} / {context.cluster_id}", width),
             fill(context_line, width)]
    if result.freshness.stale:
        lines.append(fill(f"STALE observation: {result.freshness.age_seconds}s old. Refresh before relying on these estimates.", width))
    lines.append("")
    if rows:
        if tabular:
            lines.append(_line((heading for _, heading in _RUNNING_ESTIMATE_COLUMNS), widths))
        for row, item in zip(rows, items, strict=True):
            if tabular:
                cells = (row[key].rjust(size) if key in {"gross", "cash"} else row[key]
                         for (key, _), size in zip(_RUNNING_ESTIMATE_COLUMNS, widths, strict=True))
                lines.append(_line(cells, widths))
            else:
                lines.extend(f"{heading}: {row[key]}" for key, heading in _RUNNING_ESTIMATE_COLUMNS)
            uncertainty = [code for code in item.values["uncertainty"]
                           if not (code == "job_not_started" and item.values["estimate_status"] == "not_started")]
            if uncertainty:
                label = "Partial estimate" if item.values["estimate_status"] == "partial" else "Details"
                reasons = "; ".join(code.replace("_", " ") for code in uncertainty)
                lines.append(fill(f"{label}: {reasons}", width, initial_indent="  ", subsequent_indent="  "))
            if row["state"] in {"SETTLING", "TERMINAL_GAP"}:
                lines.append(fill("Observation gap; settlement is not confirmed.", width,
                                  initial_indent="  ", subsequent_indent="  "))
            if not tabular:
                lines.append("")
    else:
        lines.append("No running estimates in this scope.")
    if lines[-1] == "":
        lines.pop()
    if any(item.values["gross_cny"] is not None for item in items):
        lines.extend(("", fill("Standard and cash price the same usage; final charges may differ.", width)))
    lines.append("")
    if isinstance(result, RunningEstimateResult):
        lines.append(fill(f"As of: {_site_time(result.as_of, timezone_name=timezone_name)}", width))
    lines.extend((fill(f"Observed: {_site_time(result.freshness.observed_at, timezone_name=timezone_name)}", width),
                  fill(f"Source: {result.freshness.source} | Age: {result.freshness.age_seconds}s", width)))
    return "\n".join(lines) + "\n"
