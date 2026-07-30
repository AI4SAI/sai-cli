"""Deterministic JSON and plain-text table output."""

from __future__ import annotations

import json
from typing import Any, Iterable

from .contracts import JobItem, JobResult


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


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


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


def _truncate(text: str, maximum: int) -> str:
    if len(text) <= maximum:
        return text
    if maximum <= 3:
        return text[:maximum]
    return f"{text[:maximum - 3]}..."


def _line(values: Iterable[str], widths: list[int]) -> str:
    cells = [value.ljust(width) for value, width in zip(values, widths, strict=True)]
    return "  ".join(cells).rstrip()


def render_table(result: JobResult) -> str:
    rows = [_row(item) for item in result.items]
    widths: list[int] = []
    for key, heading, maximum in _COLUMNS:
        widest = max([len(heading), *(len(row[key]) for row in rows)], default=len(heading))
        widths.append(min(widest, maximum))

    lines = [
        f"Site: {result.site_id}  Scope: {result.scope}  Source: {result.freshness.source}  Queried: {result.freshness.queried_at}",
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
    return "\n".join(lines) + "\n"
