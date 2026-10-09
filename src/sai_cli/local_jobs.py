"""Local job queries shared by the CLI and the site's familiar stat_job entry."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any, Mapping

from .contracts import JobItem, short_job_state
from .errors import ConfigError, ContractError
from .native_process import read_native_json
from .native_values import (invalid_native as _invalid, native_number as _number,
                            native_text as _text, local_options, native_environment,
                            native_header, native_user)
from .render import _duration
from .render import _line, _truncate


def _timestamp(value: int | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError) as exc:
        raise _invalid() from exc


def _memory(job: dict[str, Any]) -> str | None:
    per_tres = _text(job.get("memory_per_tres"))
    if per_tres:
        gpu = re.fullmatch(r"gpu:(?:[^:]+:)?(\d+)", per_tres)
        return _memory_unit(int(gpu[1]), "GPU") if gpu else f"{per_tres} MiB/TRES"
    for key, unit in (("memory_per_cpu", "CPU"), ("memory_per_node", "node")):
        amount = _number(job.get(key))
        if amount is not None:
            return _memory_unit(amount, unit)
    return None


def _memory_unit(amount: int, unit: str) -> str:
    size = f"{amount // 1024}G" if amount and amount % 1024 == 0 else f"{amount}M"
    return f"{size}/{unit}"


def _item(job: object, *, observed: int) -> JobItem:
    if not isinstance(job, dict):
        raise _invalid()
    job_id = _number(job.get("job_id"))
    if not job_id:
        raise _invalid()
    array_job = _number(job.get("array_job_id"))
    task = _number(job.get("array_task_id"))
    tasks = _text(job.get("array_task_string"))
    states = job.get("job_state")
    if not isinstance(states, list) or not states:
        raise _invalid()
    states = [_text(state, required=True) for state in states]
    state = short_job_state(states[0])
    submitted = _number(job.get("submit_time"))
    started = _number(job.get("start_time"))
    elapsed = None
    waited = None
    if state == "PD":
        started = None  # A pending job's start_time is a forecast, not execution.
        if submitted is not None and submitted <= observed:
            waited = observed - submitted
    elif state in {"R", "S", "CG", "CD", "F", "CA"} and started:
        suspended = _number(job.get("suspend_time"))
        previous = _number(job.get("pre_sus_time"))
        ended = observed if state in {"R", "S"} else _number(job.get("end_time"))
        if suspended is not None and previous is not None and ended and started <= ended <= observed:
            if (not suspended and previous == 0) or (started <= suspended <= ended and previous <= suspended - started):
                elapsed = previous if state == "S" else ended - (suspended or started) + previous
                waited = elapsed
    gres = _text(job.get("tres_per_node")) or ""
    gpu_counts = re.findall(r"(?:^|,)gres/gpu(?::([^,:]+))?:(\d+)(?=,|$)", gres)
    totals = [int(count) for kind, count in gpu_counts if not kind]
    gpu_count = totals[0] if len(totals) == 1 else sum(int(count) for _, count in gpu_counts) if gpu_counts else None
    values = {
        "job_id": str(array_job or job_id),
        "array_task_id": (str(task) if task is not None else f"[{tasks}]" if tasks else None) if array_job else None,
        "name": _text(job.get("name")), "slurm_user": _text(job.get("user_name")),
        "slurm_account": _text(job.get("account")),
        "state": state, "state_label": ",".join(states), "priority": _number(job.get("priority")),
        "submit_time": _timestamp(submitted), "start_time": _timestamp(started),
        "elapsed_seconds": elapsed, "run_wait_seconds": waited,
        "partition": _text(job.get("partition")), "qos": _text(job.get("qos")),
        "nodes": _number(job.get("node_count")),
        "slots": _number(job.get("tasks" if state == "PD" else "cpus")),
        "gpus_per_node": gpu_count, "mem_per_unit": _memory(job),
        "reason_or_nodelist": _text(job.get("state_reason" if state == "PD" else "nodes")),
    }
    try:
        return JobItem.from_payload(values, request_id="native-squeue",
                                    text_limits={key: 16384 for key in values})
    except ContractError as exc:
        raise _invalid() from exc


@dataclass(frozen=True)
class LocalJobs:
    cluster: str
    actor: str
    uid: int
    filters: dict[str, str | None]
    observed_at: str
    items: tuple[JobItem, ...]
    has_more: bool
    warning_count: int

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "native.jobs/v1", "source": "squeue", "authority": "native",
                "cluster": self.cluster, "actor": {"user": self.actor, "uid": self.uid},
                "filters": self.filters, "observed_at": self.observed_at,
                "items": [item.as_dict() for item in self.items], "count": len(self.items),
                "has_more": self.has_more, "warning_count": self.warning_count}


def read_local_jobs(args: argparse.Namespace, *, environ: Mapping[str, str]) -> LocalJobs:
    timeout = local_options(args, command="jobs local")
    if args.limit is not None and not 1 <= args.limit <= 100000:
        raise ConfigError("--limit must be between 1 and 100000")
    actor = native_user()
    filters = {key: getattr(args, key) for key in ("users", "accounts", "partition", "qos", "states")}
    for value in filters.values():
        if value is not None and (not value.strip() or len(value) > 4096
                                  or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
            raise ConfigError("native filters must be nonempty text without control characters")
    # Preserve stat_job: unfiltered means myself; explicit queue filters use
    # native-visible matching jobs. '*' is its explicit all-users spelling.
    if not any(filters.values()):
        filters["users"] = actor
    elif filters["users"] == "*":
        filters["users"] = None
    argv = ["squeue", "--json", "--local"]
    options = {"users": "user", "accounts": "account", "partition": "partition", "qos": "qos", "states": "states"}
    argv.extend(f"--{options[key]}={value}" for key, value in filters.items() if value is not None)
    native_env = native_environment(environ, filter_prefix="SQUEUE_")
    payload = read_native_json(argv, environ=native_env, timeout=timeout)
    cluster, warning_count = native_header(payload)
    if not isinstance(payload.get("jobs"), list):
        raise _invalid()
    observed_at = datetime.now(timezone.utc).replace(microsecond=0)
    items = tuple(_item(job, observed=int(observed_at.timestamp())) for job in payload["jobs"])
    # One display order for JSON and humans, matching the familiar state groups.
    order = {"R": 0, "PD": 1, "CG": 2, "S": 3}
    items = tuple(sorted(items, key=lambda item: (order.get(item.values["state"], 4),
                        -(item.values["run_wait_seconds"] or 0), -(item.values["priority"] or 0), item.canonical_id)))
    has_more = args.limit is not None and len(items) > args.limit
    if args.limit is not None:
        items = items[:args.limit]
    return LocalJobs(cluster=cluster, actor=actor, uid=os.geteuid(), filters=filters,
                     observed_at=observed_at.isoformat().replace("+00:00", "Z"), items=items,
                     has_more=has_more, warning_count=warning_count)


def render_local_jobs(result: LocalJobs) -> str:
    headings = ("job-ID", "Prior", "Name", "User", "Submit/Start at", "ST", "Run/Wait",
                "Partition", "QOS", "Nodes", "Slots", "GPU", "MemPerU", "array_ID", "Reason/Nodelist")
    widths = [7, 6, 13, 15, 20, 3, 12, 10, 12, 6, 6, 4, 8, 9, 15]
    rows = []
    for item in result.items:
        value = item.values
        timestamp = value["start_time"] or value["submit_time"]
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S") if timestamp else "-"
        cells = [value["job_id"], value["priority"], _truncate(value["name"] or "-", 13), value["slurm_user"],
                 timestamp, value["state"], _duration(value["run_wait_seconds"]), value["partition"], value["qos"],
                 value["nodes"], value["slots"], value["gpus_per_node"], value["mem_per_unit"],
                 value["array_task_id"], value["reason_or_nodelist"]]
        rows.append(["-" if cell is None or cell == "" else str(cell) for cell in cells])
    # Keep the familiar spacing while allowing IDs and native memory units to fit.
    for index in (0, 1, 3, 5, 7, 8, 9, 10, 11, 12, 13):
        widths[index] = max(widths[index], *(len(cells[index]) for cells in rows)) if rows else widths[index]
    lines = [_line(headings, widths, gap=1), "-" * (sum(widths) + len(widths) - 1)]
    lines.extend(_line(cells, widths, gap=1) for cells in rows)
    if not rows:
        lines.append("(no jobs)")
    lines.extend(("Note: 1. 'GPU' indicates the per-node GPU request.",
                  "      2. 'MemPerU' retains its native /GPU, /CPU or /node memory unit."))
    if result.has_more:
        lines.append("More jobs matched; increase --limit or narrow the query.")
    return "\n".join(lines) + "\n"
