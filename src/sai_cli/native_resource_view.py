"""Rich resource tables over one native Slurm observation."""
from __future__ import annotations

from decimal import Decimal
from io import StringIO
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .local_resources import LocalResources, _available, _ready
from .render import format_decimal


FREE = "bright_green"
ALLOCATED = "bright_blue"
BLOCKED = "bright_red"
UNKNOWN = "bright_yellow"


def _number(value: int | None) -> str:
    return "?" if value is None else str(value)


def _gib(value: int | None) -> str:
    return "?" if value is None else format_decimal(str(Decimal(value) / 1024), 1, trim=True)


def _state(node: dict[str, Any], ready: bool | None) -> Text:
    names = {"ALLOCATED": "ALLOC", "COMPLETING": "COMP", "NOT_RESPONDING": "NO_RESP", "MAINTENANCE": "MAINT"}
    label = "+".join(names.get(state, state) for state in node["states"]) or "UNKNOWN"
    style = BLOCKED if ready is False else UNKNOWN if ready is None else FREE if "IDLE" in node["states"] else ALLOCATED
    return Text(label, style=style)


def _qos(part: dict[str, Any]) -> str:
    qos = part["qos"]
    value = qos["allowed"] if qos["allowed"] is not None else "?"
    if qos["deny"]:
        value += " (deny: " + qos["deny"] + ")"
    return value or "ALL"


def _table(*headers: str) -> Table:
    table = Table(box=box.SIMPLE_HEAD, padding=(0, 1), pad_edge=False,
                  show_edge=False, header_style="bold", collapse_padding=True)
    for header in headers:
        table.add_column(header, overflow="fold")
    return table


def _allocation(used: int | None, total: int | None, *, memory: bool = False, bars: int = 10,
                ready: bool | None = True) -> Table:
    label = _gib if memory else _number
    row = Table.grid(padding=(0, 1), expand=True)
    if bars and total is not None and used is not None and 0 <= used <= total and total > 0:
        style = FREE if ready is True else BLOCKED if ready is False else UNKNOWN
        row.add_column(width=bars)
        row.add_column(no_wrap=True, justify="right", ratio=1)
        row.add_row(ProgressBar(total=total, completed=used, width=bars, style=style,
                                complete_style=ALLOCATED, finished_style=ALLOCATED),
                    Text(f"{label(used)}/{label(total)}"))
    else:
        row.add_row(Text(f"{label(used)}/{label(total)}"))
    return row


def _gpu_matrix(node: dict[str, Any], ready: bool | None) -> Columns | Text:
    gpu = node["gpu"]
    indices, total = gpu["allocated_indices"], gpu["configured_units"]
    if indices is None or total is None:
        return Text("?", style=UNKNOWN)
    idle = FREE if ready is True else BLOCKED if ready is False else UNKNOWN
    occupied = set(indices)
    return Columns([Text("[#]" if index in occupied else "[_]",
                         style=ALLOCATED if index in occupied else idle)
                    for index in range(total)], padding=0, equal=True)


def _gpu_nodes(value: dict[str, Any], width: int = 120) -> Table:
    compact = width < 64
    table = _table("Node" if compact else "NodeName", "State" if compact else "Status",
                   *([] if compact else ["Partition"]), "GPU", "GPU (IDX)")
    table.columns[0].min_width = 6
    table.columns[-2].no_wrap = True
    table.columns[-1].min_width = 3
    table.columns[-1].max_width = max(node["gpu"]["configured_units"] or 1 for node in value["nodes"]) * 3
    for part in value["partitions"]:
        for node in value["nodes"]:
            if part["name"] not in node["partitions"] or node["kind"] != "gpu":
                continue
            ready = _ready(node, [part])
            gpu = node["gpu"]
            free = _available(gpu["unallocated_units"], ready)
            amount = Text(f"{_number(free)}/{_number(gpu['configured_units'])}",
                          style="bold" if free else BLOCKED if ready is False else "")
            table.add_row(Text(node["name"]), _state(node, ready), *([] if compact else [Text(part["name"])]), amount, _gpu_matrix(node, ready))
    return table


def _cpu_nodes(value: dict[str, Any], width: int) -> Group:
    blocks = []
    bars = 10 if width >= 100 else 5 if width >= 64 else 0
    reports = width >= 80
    for part in value["partitions"]:
        members = [node for node in value["nodes"] if part["name"] in node["partitions"] and node["kind"] != "gpu"]
        if not members:
            continue
        blocks.append(Text.assemble((part["name"], "bold bright_magenta"), "  QOS ", _qos(part), overflow="ellipsis", no_wrap=True))
        table = _table("Node" if width < 64 else "NodeName", "State" if width < 64 else "Status",
                       "CPU\nalloc/total" if width < 64 else "CPU\nalloc / total",
                       "GiB\nalloc/total" if width < 64 else "Mem GiB\nalloc / total",
                       *(["Load", "Free GiB"] if reports else []))
        if reports:
            table.columns[-2].justify = table.columns[-1].justify = "right"
        for node in members:
            ready = _ready(node, [part])
            cpu, memory, reported = node["cpu"], node["memory"], node["reported"]
            cells = [Text(node["name"]), _state(node, ready),
                     _allocation(cpu["allocated"], cpu["effective_total"], bars=bars, ready=ready),
                     _allocation(memory["allocated_mib"], memory["effective_mib"], memory=True, bars=bars, ready=ready)]
            if reports:
                load = reported["cpu_load_hundredths"]
                cells.extend((Text("?" if load is None else format_decimal(str(Decimal(load) / 100), 1, trim=True)),
                              Text(_gib(reported["free_memory_mib"]))))
            table.add_row(*cells)
        blocks.extend((table, Text("")))
    return Group(*blocks)


def _summary(value: dict[str, Any], family: str, width: int) -> Table:
    gpu = family == "gpu"
    show_qos = width >= 64
    table = _table("Partition", "TotGPU" if gpu else "TotCPU", "Avail", "Allocated",
                   *(["Allowed QOS"] if show_qos else []))
    if show_qos:
        table.columns[-1].max_width = min(70, width // 3)
        table.columns[-1].no_wrap = True
        table.columns[-1].overflow = "ellipsis"
    for part in [*value["partitions"], {"name": "GLOBAL", "summary": value["summary"]}]:
        resource = part["summary"][family]
        total, allocated, free = resource["capacity"], resource["allocated"], resource["free_on_ready_nodes"]
        if total == 0:
            continue
        usage = Table.grid(padding=(0, 1))
        if total and allocated is not None:
            if width >= 64:
                usage.add_row(ProgressBar(total=total, completed=allocated, width=10, style="default",
                                          complete_style=ALLOCATED, finished_style=ALLOCATED),
                              Text(f"{allocated / total:.0%}"))
            else:
                usage.add_row(Text(f"{allocated / total:.0%}"))
        else:
            usage.add_row(Text("?"))
        global_row = part["name"] == "GLOBAL"
        if global_row:
            table.add_section()
        table.add_row(Text(part["name"], style="bold bright_magenta" if global_row else ""), Text(_number(total)),
                      Text(_number(free), style="bold " + FREE if free else ""), usage,
                      *([Text("" if global_row else _qos(part))] if show_qos else []))
    return table


def resource_view(result: LocalResources, *, details: bool = False, width: int = 120) -> Group:
    value = result.values
    if not value["nodes"]:
        return Group(Text("No native nodes matched this query."))
    blocks = []
    kind = value["filters"]["kind"]
    if kind != "cpu" and any(node["kind"] == "gpu" for node in value["nodes"]):
        if details:
            blocks.extend((_gpu_nodes(value, width), Text.assemble("GPU: Free/Total  ", ("[_] Idle", FREE), "  ", ("[#] Alloc", ALLOCATED), "  ? Unknown"), Text("")))
        blocks.append(_summary(value, "gpu", width))
    if kind != "gpu":
        blocks.append(_cpu_nodes(value, width) if details else _summary(value, "cpu", width))
    if value["unclassified_nodes"]:
        blocks.append(Text(f"Unknown GPU configuration: {value['unclassified_nodes']} nodes", style=UNKNOWN))
    return Group(*blocks)


def render_local_resources(result: LocalResources, *, details: bool = False, width: int = 120, color: bool = False) -> str:
    output = StringIO()
    console = Console(file=output, width=max(40, width), height=25, force_terminal=color, color_system="standard" if color else None,
                      no_color=not color, highlight=False, markup=False)
    console.print(resource_view(result, details=details, width=console.width))
    return output.getvalue().rstrip() + "\n"
