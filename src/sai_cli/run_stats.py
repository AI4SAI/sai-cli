"""Allowlisted step observations; allocated resources and utilization stay separate."""
from dataclasses import dataclass
from datetime import datetime
import re

from .errors import ContractError
from .managed_runs import ManagedReadResult, _context, _integer, _object, _text, _time, _token
from .messages import Messages


_INTEGER_MAX = 9007199254740991
_STEP = re.compile(r"([1-9][0-9]{0,19})\.(?:0|[1-9][0-9]*|batch|extern|interactive)")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_BYTE_FIELDS = ("average_rss_bytes", "maximum_task_rss_bytes")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _nullable_counter(row: dict, key: str, request_id: str) -> int | None:
    if key not in row:
        raise ContractError(request_id=request_id)
    return None if row[key] is None else _integer(row, key, request_id, maximum=_INTEGER_MAX)


@dataclass(frozen=True)
class ManagedRunStats(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str,
                     run_ref: str, request_id: str) -> "ManagedRunStats":
        data, result = _context(payload, "compute.run-stats/v1", workspace_key, site_id, request_id)
        status = _text(data, "status", request_id)
        if (_token(data, "run_ref", request_id) != run_ref or data.get("source") != "slurm_sstat"
                or status not in {"available", "not_running", "unavailable"}
                or "sampled_at" not in data or data["sampled_at"] is not None):
            raise ContractError(request_id=request_id)
        started, finished = (_time(data, key, request_id, nullable=True) for key in ("read_started_at", "read_finished_at"))
        if ((started is None) != (finished is None)
                or (started is not None and _instant(started) > _instant(finished))):
            raise ContractError(request_id=request_id)
        if "execution" not in data or not isinstance(data.get("steps"), list) or len(data["steps"]) > 64:
            raise ContractError(request_id=request_id)
        execution = None
        steps = []
        if status == "available":
            if started is None or not data["steps"]:
                raise ContractError(request_id=request_id)
            native = _object(data["execution"], request_id)
            execution = {"sluid": _token(native, "sluid", request_id, pattern=re.compile(r"s[0-9A-HJKMNP-TV-Z]{13}")),
                         "submit_time": _time(native, "submit_time", request_id),
                         "start_time": _time(native, "start_time", request_id),
                         "restart_count": _integer(native, "restart_count", request_id, maximum=_INTEGER_MAX),
                         "resize_time": _time(native, "resize_time", request_id, nullable=True)}
            for item in data["steps"]:
                row = _object(item, request_id)
                reference = _text(row, "step_ref", request_id, maximum=64)
                if _STEP.fullmatch(reference) is None:
                    raise ContractError(request_id=request_id)
                nodes = row.get("nodes")
                if (not isinstance(nodes, list) or not 1 <= len(nodes) <= 4096
                        or any(not isinstance(node, str) or _NODE.fullmatch(node) is None for node in nodes)
                        or len(set(nodes)) != len(nodes)):
                    raise ContractError(request_id=request_id)
                step = {"step_ref": reference, "nodes": list(nodes),
                        "task_count": _nullable_counter(row, "task_count", request_id),
                        "average_cpu_seconds": _nullable_counter(row, "average_cpu_seconds", request_id)}
                for key in _BYTE_FIELDS:
                    value = _text(row, key, request_id, nullable=True, maximum=20)
                    if value is not None and re.fullmatch(r"0|[1-9][0-9]*", value) is None:
                        raise ContractError(request_id=request_id)
                    step[key] = value
                steps.append(step)
            if (len({step["step_ref"] for step in steps}) != len(steps)
                    or len({step["step_ref"].split(".", 1)[0] for step in steps}) != 1):
                raise ContractError(request_id=request_id)
        elif data["execution"] is not None or data["steps"]:
            raise ContractError(request_id=request_id)
        return cls({**result, "run_ref": run_ref, "source": "slurm_sstat", "status": status,
                    "queried_at": _time(data, "queried_at", request_id), "read_started_at": started,
                    "read_finished_at": finished, "sampled_at": None, "execution": execution, "steps": steps})


def stats_lines(result: ManagedRunStats, language: str = "en-US") -> list[str]:
    t, data = Messages(language), result.values
    value = lambda item: t("unknown") if item is None else str(item)
    lines = [t("runtime_stats") + " · " + t("stats_" + data["status"]), t("stats_meaning")]
    for step in data["steps"]:
        lines.extend((step["step_ref"], f"{t('stats_cpu')}: {value(step['average_cpu_seconds'])}",
                      f"{t('stats_rss')}: {value(step['average_rss_bytes'])}",
                      f"{t('stats_max_rss')}: {value(step['maximum_task_rss_bytes'])}",
                      f"{t('stats_tasks')}: {value(step['task_count'])}", f"{t('nodes')}: {', '.join(step['nodes'])}", ""))
    lines.extend(("", t("stats_window") + ": " + (t("stats_no_read") if data["read_started_at"] is None
                  else f"{data['read_started_at']} → {data['read_finished_at']}"),
                  t("stats_sample_unknown"), t("queried", time=data["queried_at"])))
    if data["execution"] is not None:
        native = data["execution"]
        lines.extend((f"SLUID: {native['sluid']}", f"{t('submitted')}: {native['submit_time']}",
                      f"{t('started')}: {native['start_time']}", f"{t('restart')}: {native['restart_count']}",
                      f"{t('stats_resize')}: {value(native['resize_time'])}"))
    return lines


def render_run_stats(result: ManagedRunStats) -> str:
    data = result.values
    return "\n".join([f"Run: {data['run_ref']} · Read scope: {data['workspace_key']} · Site: {data['site_id']}",
                      *stats_lines(result)]) + "\n"
