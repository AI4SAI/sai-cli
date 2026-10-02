"""Localized terminal layouts over validated read DTOs, with no new facts."""
from datetime import datetime, timedelta, timezone

from rich.console import Group
from rich.table import Table
from rich.text import Text

from .contracts import JobCostResult, short_job_state
from .managed_runs import ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts, terminal_log
from .native_quota import NativeQuotaResult
from .render import format_allocation_indices, format_decimal
from .site_jobs import SiteJobAllocationResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary
from .tui_messages import MESSAGES, Messages


def display(value: object, language: str = "en-US") -> str:
    return Messages(language)("unknown") if value is None else " ".join(str(value).split())


def state_text(value: str, t: Messages) -> str:
    key = {"R": "running", "PD": "queued", "S": "suspended", "CG": "completing", "CD": "completed",
           "F": "failed", "CA": "canceled"}.get(short_job_state(value), value)
    return t(key) if key in MESSAGES else value


def task_state(value: str, t: Messages) -> Text:
    style = {"completed": "#79b98b", "failed": "#de8b8d", "needs_attention": "#d8b471"}.get(value, "")
    return Text(state_text(value, t), style=style)


def modified_time_text(nanoseconds: int, language: str = "en-US") -> str:
    t = Messages(language)
    try:
        instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=nanoseconds // 1_000_000_000)
    except OverflowError:
        return t("modified_range", value=nanoseconds)
    return t("modified_utc", time=instant.strftime("%Y-%m-%d %H:%M:%S"))


def task_detail_panel(result: ManagedRunDetail, language: str = "en-US") -> Group:
    t = Messages(language)
    run = result.values["run"]
    title = terminal_log(run["title"]) if run["title"] is not None else t("untitled")
    lines = [f"{t('run')}: {run['run_ref']}", f"{t('cluster')}: {run['cluster_id']}",
             f"{t('scheduler')}: {run['scheduler_ref'] or t('not_assigned')}",
             f"{t('scheduler_state')}: {run['scheduler_state'] or t('unknown')}",
             f"{t('revision')}: {run['state_revision']}"]
    lines += [f"{t(field)} UTC: {run[field] or t('unknown')}" for field in
              ("accepted_at", "queued_at", "started_at", "finished_at")]
    if run["error_code"] is not None:
        lines.append(f"{t('error_code')}: {run['error_code']}")
    return Group(Text(title, style="bold", overflow="fold"),
                 task_state(run["status"], t), Text("\n".join(lines)),
                 Text(t("task_receipt", time=run["last_observed_at"] or t("unknown"))))


def task_file_panel(result: ManagedRunLogs | ManagedRunArtifacts, language: str = "en-US") -> Group:
    t, data = Messages(language), result.values
    page = t("last_page" if data["complete"] else "more_pages")
    if isinstance(result, ManagedRunLogs):
        if not data["available"]:
            return Group(Text(t("log_pending")))
        return Group(Text(f"{t(data['stream'])} · {page}"), Text(terminal_log(data["content"]) if data["content"] else t("log_empty")))
    if not data["items"]:
        return Group(Text(t("files_empty")), Text(page))
    rows = []
    for item in data["items"]:
        rows.extend((Text(terminal_log(item["relative_path"]), style="bold", overflow="fold"),
                     Text(t("bytes", count=item["size_bytes"])),
                     Text(modified_time_text(item["modified_at_ns"], language), overflow="fold"), Text("")))
    return Group(*rows, Text(page))


def task_artifact_option(item: dict, language: str, *, selected: bool = False) -> Text:
    t = Messages(language)
    prompt = Text(overflow="fold", no_wrap=False)
    if selected:
        prompt.append(t("file_selected") + "\n", style="bold")
    prompt.append(terminal_log(item["relative_path"]), style="bold")
    prompt.append("\n" + t("bytes", count=item["size_bytes"]))
    prompt.append("\n" + modified_time_text(item["modified_at_ns"], language))
    return prompt


def resource_panel(candidate: dict | None, compared: list[dict], language: str, width: int) -> Group:
    t = Messages(language)
    fields = (("cpu_model", "cpu"), ("cpu_cores_per_node", "cores_node"),
              ("gpu_model", "gpu"), ("gpu_count", "gpu_total"), ("node_count", "nodes"))

    def facts(row: dict) -> list[tuple[str, str]]:
        return [(t(label), display(row[key], language)) for key, label in fields] + [
            ("QOS", ", ".join(row["supported_qos"]) or t("unknown")),
            (t("price"), row["pricing"]["display"] if row["pricing"] else t("unknown")),
        ]

    content: list = []
    if candidate is not None:
        content.append(Text(f"{t('resource_candidate')}: {candidate['title']}", style="bold", overflow="fold"))
        content.append(Text(candidate["name"], overflow="fold"))
        if candidate["summary"]:
            content.append(Text(candidate["summary"], overflow="fold"))
        if candidate["scenarios"]:
            content.append(Text(f"{t('resource_scenarios')}: " + " · ".join(candidate["scenarios"]), overflow="fold"))
        content.append(Text("\n".join(f"{label}: {value}" for label, value in facts(candidate)), overflow="fold"))
    else:
        content.append(Text(t("resource_choose")))
    if compared:
        content.append(Text("\n" + t("resource_comparison"), style="bold"))
        if width >= 80 and len(compared) == 2:
            table = Table(box=None, expand=True, padding=(0, 1))
            table.add_column(t("specification"), ratio=1)
            for row in compared:
                table.add_column(Text(row["title"]), ratio=2)
            for index, (label, _) in enumerate(facts(compared[0])):
                table.add_row(Text(label), *(Text(facts(row)[index][1], overflow="fold") for row in compared))
            content.append(table)
        else:
            for row in compared:
                content.append(Text(row["title"], style="bold", overflow="fold"))
                content.append(Text("\n".join(f"{label}: {value}" for label, value in facts(row)), overflow="fold"))
    content.append(Text("\n" + t("resource_meaning"), overflow="fold"))
    return Group(*content)


def allocation_panel(result: SiteJobAllocationResult, language: str = "en-US") -> Group:
    t, job, freshness = Messages(language), result.job.values, result.freshness
    status = "allocation_unavailable" if result.allocation_status == "unavailable" else result.allocation_status
    header = Text("\n".join((
        f"{t('job')}: {result.job.canonical_id} · {display(job['name'], language)}",
        f"{t('state')}: {', '.join(result.scheduler_states)} · {t('restart')}: {display(result.restart_count, language)}",
        f"{t('submitted')}: {display(job['submit_time'], language)}",
        f"{t('started')}: {display(job['start_time'], language)}",
        f"{t('source')}: {freshness.source} · {t('observed', time=freshness.observed_at)}",
        t("age", seconds=freshness.age_seconds) + " · " + t("stale" if freshness.stale else "fresh"), t(status),
    )))
    table = Table(box=None, expand=True, padding=(0, 1))
    for column in ("nodes", "allocated_cpus", "memory_mib"):
        table.add_column(t(column))
    for node in result.nodes or ():
        table.add_row(Text(node.name), Text(str(node.cpus)), Text(display(node.memory_mib, language)))
    hint = Text(t("snapshot_paused"))
    if not result.nodes:
        return Group(header, hint)
    resources: list[Text] = [Text(t("allocated_gres"), style="bold")]
    for node in result.nodes:
        resources.append(Text(node.name, style="bold", overflow="fold"))
        if node.gres is None:
            resources.append(Text(t("unknown")))
        else:
            for item in node.gres:
                resource = item.name + (":" + item.type if item.type is not None else "")
                indices = t("unknown") if item.indices is None else format_allocation_indices(item.indices)
                resources.append(Text(f"{resource} · {t('gres_count', count=item.count)}\n"
                                      f"{t('gres_indices')}: {indices}", overflow="fold"))
    return Group(header, table, *resources, Text(t("gres_units_hint")), hint)


def placement_panel(result: SiteJobPlacementResult, language: str = "en-US") -> Group:
    t = Messages(language)
    rows = [Text(f"{t('placement')} · {result.allocation.job.canonical_id}", style="bold")]
    for node in result.nodes:
        registration = node.registration
        rows.append(Text(node.name, style="bold", overflow="fold"))
        if registration is None:
            rows.append(Text(t("placement_expired" if node.status == "expired" else "placement_unmapped")))
            continue
        rack = registration.rack
        location = t("unknown") if rack is None else t("placement_rack", label=rack.label, start=rack.u_start, height=rack.u_height)
        rows.extend((Text(registration.label, overflow="fold"), Text(location, overflow="fold"),
                     Text(f"{t('placement_verified')}: {registration.verified_at}"),
                     Text(f"{t('placement_until')}: {registration.valid_until}")))
    if result.inventory is not None:
        rows.append(Text(f"{t('placement_published')}: {result.inventory.published_at}"))
    return Group(*rows, Text(t("placement_meaning")), allocation_panel(result.allocation, language))


def storage_panel(result: StorageQuotaSummary | NativeQuotaResult, language: str, *, workspace_label: str | None = None) -> Group:
    t, data = Messages(language), result.values
    workspace = workspace_label or data["workspace_key"]
    if isinstance(result, StorageQuotaSummary):
        fields = (("state", "state", ""), ("effective_total_tib", "effective", " TiB"),
                  ("used_tib", "used", " TiB"), ("remaining_tib", "remaining", " TiB"),
                  ("target_total_tib", "target", " TiB"), ("used_inodes", "inodes", ""),
                  ("observed_soft_limit_tib", "soft_limit", " TiB"), ("observed_hard_limit_tib", "hard_limit", " TiB"),
                  ("inode_soft_limit", "soft_limit", " / " + t("inodes")), ("inode_hard_limit", "hard_limit", " / " + t("inodes")),
                  ("observed_at", "last_observed_at", ""), ("quota_updated_at", "quota_updated", ""))
        lines = ([] if workspace_label else [t('storage_context', workspace=workspace)]) + [f"{t('source')}: {t(data['source'])}"]
        for key, label, unit in fields:
            value = state_text(data[key], t) if key == "state" else display(data[key], language)
            lines.append(f"{t(label)}{unit}: {value}")
        return Group(Text("\n".join(lines)))
    rows = ([] if workspace_label else [Text(t("storage_context", workspace=workspace))]) + [Text(f"{t('source')}: {t(data['source'])}")]
    for item in data["items"]:
        rows.append(Text(item["label"], style="bold"))
        rows.append(Text(f"{t('quota_ref')}: {item['quota_ref']} · {t('kind')}: {t('quota_kind_' + item['kind'])}"))
        rows.append(Text(t("observed", time=item["observed_at"])))
        for field, label in (("used_bytes", "used"), ("block_soft_bytes", "soft_limit"), ("block_hard_bytes", "hard_limit"),
                             ("used_inodes", "inodes"), ("inode_soft", "soft_limit"), ("inode_hard", "hard_limit")):
            unit = (t("unlimited") if field not in {"used_bytes", "used_inodes"} and item[field] == "0"
                    else t("bytes", count=item[field]) if field.endswith("bytes") else item[field])
            rows.append(Text(f"{t(label)}: {unit}"))
    return Group(*rows, Text(t("native_zero")))


def job_cost_panel(result: JobCostResult, language: str = "en-US") -> Group:
    """Present one job observation and its non-final price without recomputing it."""
    t = Messages(language)
    job, estimate, freshness = result.observation.items[0], result.estimate.values, result.freshness
    unavailable = t("not_started" if estimate["estimate_status"] == "not_started" else "unavailable")
    gross = f"{format_decimal(estimate['gross_cny'])} CNY" if estimate["gross_cny"] is not None else unavailable
    cash = (f"{format_decimal(estimate['cash_before_credit_cny'])} CNY" if estimate["cash_before_credit_cny"] is not None
            else t("cash_restricted") if "cash_price_restricted" in estimate["uncertainty"] else unavailable)
    facts = Table(box=None, show_header=False, expand=True, padding=(0, 1))
    facts.add_column(ratio=1)
    facts.add_column(ratio=1)
    for label, value in (("state", state_text(job.values["state"], t)), ("estimate", state_text(estimate["estimate_status"], t)),
                         ("gross", gross), ("before_credit", cash)):
        facts.add_row(Text(t(label)), Text(value))
    resources = estimate["resources"]
    if resources["usage_quantity"] is not None:
        quantity = format_decimal(resources["usage_quantity"], 4, trim=True)
        unit = t("gpu_hours" if resources["resource_type"].upper() == "GPU" else "cpu_hours")
        facts.add_row(Text(t("cost_quantity")), Text(f"{quantity} {unit}"))
    messages = []
    if any(code not in {"cash_price_restricted", "job_not_started"} for code in estimate["uncertainty"]):
        messages.append(Text(t("estimate_incomplete")))
    return Group(Text(f"{t('job')} {job.canonical_id} · {t('non_final')}", style="bold"), facts, *messages,
                 Text(t("observed", time=freshness.observed_at)),
                 Text(f"{t('source')}: {freshness.source} · {t('stale' if freshness.stale else 'fresh')}"),
                 Text(t("snapshot_paused")))
