"""Local job queries shared by the CLI and the site's familiar stat_job entry."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
import re
from typing import Any, Mapping

from .contracts import JobItem, short_job_state
from .errors import ConfigError, ContractError, UnavailableError
from .native_process import read_native_json
from .render import job_table_lines


def add_local_job_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-A", "--account", "--accounts", dest="accounts", help="native Slurm account(s), comma-separated")
    parser.add_argument("-u", "--user", "--users", dest="users", help="native user(s); '*' selects all native-visible users")
    parser.add_argument("-p", "--partition", help="native partition(s)")
    parser.add_argument("-q", "--qos", help="native QOS name(s)")
    parser.add_argument("-t", "--states", "--status", dest="states", help="native states, such as R,PD")
    parser.add_argument("--limit", type=int, default=None, help="maximum returned rows; JSON reports has_more when limited")


def _invalid() -> ContractError:
    return ContractError("Slurm returned invalid job data", code="native_response_invalid")


def _text(value: object, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > 4096 or (required and not value):
        raise _invalid()
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise _invalid() from exc
    # Job names are data, including control characters accepted by Slurm.
    return "".join(f"\\x{ord(char):02x}" if ord(char) < 32 or 127 <= ord(char) <= 159 else char
                   for char in value)


def _number(value: object) -> int | None:
    if isinstance(value, dict):
        if type(value.get("set")) is not bool or type(value.get("infinite")) is not bool:
            raise _invalid()
        if not value["set"] or value["infinite"]:
            return None
        value = value.get("number")
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < 2**63:
        raise _invalid()
    return value


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
    try:
        import pwd
    except ImportError as exc:
        raise UnavailableError("local Slurm queries require a Unix native environment",
                               code="native_client_unavailable") from exc
    for name in ("config", "profile", "base_url", "site", "cluster", "cache", "no_cache", "allow_insecure_http"):
        if getattr(args, name, None) not in (None, False):
            raise ConfigError(f"jobs local uses this host's native Slurm context, not --{name.replace('_', '-')}")
    timeout = args.timeout if args.timeout is not None else 10.0
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ConfigError("--timeout must be greater than zero and at most 120 seconds")
    if args.limit is not None and not 1 <= args.limit <= 100000:
        raise ConfigError("--limit must be between 1 and 100000")
    actor = pwd.getpwuid(os.geteuid()).pw_name
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
    native_env = {key: value for key, value in environ.items() if not key.startswith(("SQUEUE_", "SAI_", "_SAI_"))}
    payload = read_native_json(argv, environ=native_env, timeout=timeout)
    if not isinstance(payload.get("errors"), list) or not isinstance(payload.get("warnings"), list):
        raise _invalid()
    if payload["errors"]:
        raise UnavailableError("Slurm reported a query error", code="native_query_failed")
    meta = payload.get("meta")
    slurm = meta.get("slurm") if isinstance(meta, dict) else None
    if not isinstance(slurm, dict) or not isinstance(payload.get("jobs"), list):
        raise _invalid()
    cluster = _text(slurm.get("cluster"), required=True)
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
                     has_more=has_more, warning_count=len(payload["warnings"]))


def render_local_jobs(result: LocalJobs) -> str:
    selection = ", ".join(f"{key}={value}" for key, value in result.filters.items() if value is not None)
    lines = [f"Slurm: {result.cluster} | {selection or 'native-visible jobs'} | Times: UTC",
             *job_table_lines(result.items, notes=(
                 "GPU is the per-node request; memory retains its native CPU/node/TRES unit. Allocation is not utilization.",
             ))]
    if result.has_more:
        lines.append("More jobs matched; increase --limit or narrow the query.")
    return "\n".join(lines) + "\n"
