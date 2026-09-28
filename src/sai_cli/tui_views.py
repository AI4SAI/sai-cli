"""Localized terminal layouts over validated read DTOs, with no new facts."""
from datetime import datetime, timedelta, timezone

from rich.console import Group
from rich.table import Table
from rich.text import Text

from .managed_runs import ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts, terminal_log
from .native_quota import NativeQuotaResult
from .site_jobs import SiteJobAllocationResult
from .storage_summary import StorageQuotaSummary
from .tui_messages import MESSAGES, Messages


def display(value: object, language: str = "en-US") -> str:
    return Messages(language)("unknown") if value is None else " ".join(str(value).split())


def state_text(value: str, t: Messages) -> str:
    return t(value) if value in MESSAGES else value


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
    return Group(header, table, hint) if result.nodes else Group(header, hint)


def storage_panel(result: StorageQuotaSummary | NativeQuotaResult, language: str) -> Group:
    t, data = Messages(language), result.values
    if isinstance(result, StorageQuotaSummary):
        fields = (("state", "state", ""), ("effective_total_tib", "effective", " TiB"),
                  ("target_total_tib", "target", " TiB"), ("used_tib", "used", " TiB"),
                  ("remaining_tib", "remaining", " TiB"), ("used_inodes", "inodes", ""),
                  ("observed_soft_limit_tib", "soft_limit", " TiB"), ("observed_hard_limit_tib", "hard_limit", " TiB"),
                  ("inode_soft_limit", "soft_limit", " / " + t("inodes")), ("inode_hard_limit", "hard_limit", " / " + t("inodes")),
                  ("observed_at", "last_observed_at", ""), ("quota_updated_at", "quota_updated", ""))
        lines = [t('storage_context', workspace=data['workspace_key']), f"{t('source')}: {data['source']}"]
        for key, label, unit in fields:
            value = state_text(data[key], t) if key == "state" else display(data[key], language)
            lines.append(f"{t(label)}{unit}: {value}")
        return Group(Text("\n".join(lines)))
    rows = [Text(t("storage_context", workspace=data["workspace_key"])), Text(f"{t('source')}: {data['source']}"), Text(t("native_zero"))]
    for item in data["items"]:
        rows.append(Text(item["label"], style="bold"))
        rows.append(Text(f"{t('quota_ref')}: {item['quota_ref']} · {t('kind')}: {item['kind']}"))
        rows.append(Text(t("observed", time=item["observed_at"])))
        for field, label in (("used_bytes", "used"), ("block_soft_bytes", "soft_limit"), ("block_hard_bytes", "hard_limit"),
                             ("used_inodes", "inodes"), ("inode_soft", "soft_limit"), ("inode_hard", "hard_limit")):
            unit = t("bytes", count=item[field]) if field.endswith("bytes") else item[field]
            rows.append(Text(f"{t(label)}: {unit}"))
    return Group(*rows)
