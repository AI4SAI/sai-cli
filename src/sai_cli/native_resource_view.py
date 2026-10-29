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
    row = Table.grid(padding=(0, 1))
    if bars and total is not None and used is not None and 0 <= used <= total and total > 0:
        style = FREE if ready is True else BLOCKED if ready is False else UNKNOWN
        row.add_column(width=bars)
        row.add_column(no_wrap=True, justify="right")
        row.add_row(ProgressBar(total=total, completed=used, width=bars, style=style,
                                complete_style=ALLOCATED, finished_style=ALLOCATED),
                    Text(f"{label(used)}/{label(total)}"))
    else:
        row.add_row(Text(f"{label(used)}/{label(total)}"))
    return row


def _gpu_matrix(node: dict[str, Any], ready: bool | None, *, numbered: bool = False) -> Columns | Text:
    gpu = node["gpu"]
    indices, total = gpu["allocated_indices"], gpu["configured_units"]
    if indices is None or total is None:
        return Text("?", style=UNKNOWN)
    idle = FREE if ready is True else BLOCKED if ready is False else UNKNOWN
    unallocated = "_" if ready is True else "x" if ready is False else "?"
    occupied = set(indices)
    return Columns([Text(f"[{index if numbered else ''}{'#' if index in occupied else unallocated}]",
                         style=ALLOCATED if index in occupied else idle)
                    for index in range(total)], padding=0, equal=True)


def gpu_legend(*, chinese: bool = False, numbered: bool = False) -> Text:
    legend = Text()
    for symbol, style, zh, en in (("#", ALLOCATED, "已分配", "Allocated"), ("_", FREE, "空闲", "Idle"),
                                  ("x", BLOCKED, "不可用", "Unavailable"), ("?", UNKNOWN, "未知", "Unknown")):
        if legend:
            legend.append("  ")
        legend.append(symbol if numbered else f"[{symbol}]", style=style)
        legend.append(" " + (zh if chinese else en))
    return legend


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
                       *(["Slurm\nS×C×T", "Load", "Free GiB"] if reports else []))
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
                topology = node.get("cpu_topology")
                dimensions = "?" if topology is None else "×".join(str(topology[key]) for key in ("sockets", "cores_per_socket", "threads_per_core"))
                cells.extend((Text(dimensions), Text("?" if load is None else format_decimal(str(Decimal(load) / 100), 1, trim=True)),
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


def _resource_summary(value: dict[str, Any], width: int) -> Table:
    wide = width >= 80
    show_qos = width >= 100
    table = _table(*(("Partition", "GPU\nfree/total", "Max free\n/node", "CPU\nfree/total", "Max free\n/node",
                      "Mem GiB\nfree/total", "Max free\n/node", *(["QOS"] if show_qos else []))
                    if wide else ("Resource", "Free/total", "Max free\n/node")))
    if show_qos:
        table.columns[-1].max_width = max(10, width // 6)
        table.columns[-1].no_wrap = True
        table.columns[-1].overflow = "ellipsis"
    for column in table.columns[1:7 if wide else 3]:
        column.justify = "right"
    parts = [*value["partitions"], {"name": "TOTAL", "summary": value["summary"]}]
    for index, part in enumerate(parts):
        total = index == len(parts) - 1
        if total or (not wide and index):
            table.add_section()
        label = Text(part["name"], style="bold bright_magenta" if total or not wide else "")
        if not total and part["partition_ready"] is not True:
            label.append(" · " + ("+".join(part["states"]) or "UNKNOWN"), style=BLOCKED if part["partition_ready"] is False else UNKNOWN)
        summary = part["summary"]
        if summary["ready_nodes"] < summary["nodes"]:
            label.append(f"\nReady {summary['ready_nodes']}/{summary['nodes']}", style=UNKNOWN)
        cells, unavailable_cells = [], []
        has_unavailable = False
        if not wide:
            table.add_row(label, Text(""), Text(""))
        for family, name in (("gpu", "GPU"), ("cpu", "CPU"), ("memory", "Mem GiB")):
            resource = summary[family]
            number = _gib if family == "memory" else _number
            free, capacity, largest = (resource[key] for key in ("free_on_ready_nodes", "capacity", "largest_free_on_one_node"))
            absent = family == "gpu" and capacity == 0
            available = Text("-" if absent else f"{number(free)}/{number(capacity)}", style=UNKNOWN if free is None else "")
            maximum = Text("-" if absent else number(largest), style=UNKNOWN if largest is None else "")
            blocked = resource["blocked_unallocated"]
            unavailable = blocked is None or blocked > 0
            allocation = Text(f"{number(resource['allocated'])}/{number(blocked)}" if unavailable else "",
                              style=UNKNOWN if blocked is None else BLOCKED)
            if wide:
                cells.extend((available, maximum))
                unavailable_cells.extend((allocation, Text("")))
                has_unavailable |= unavailable
            elif not absent:
                table.add_row(Text("  " + name), available, maximum)
                if unavailable:
                    table.add_row(Text("  Alloc/blocked"), allocation, Text(""))
        if wide:
            table.add_row(label, *cells, *([Text("" if total else _qos(part))] if show_qos else []))
            if has_unavailable:
                table.add_row(Text("Alloc/blocked"), *unavailable_cells, *([Text("")] if show_qos else []))
    return table


def resource_view(result: LocalResources, *, details: bool = False, width: int = 120) -> Group:
    value = result.values
    blocks = []
    kind = value["filters"]["kind"]
    if not value["nodes"]:
        blocks.append(Text("No native nodes matched this query."))
    elif kind == "all" and not details:
        blocks.append(_resource_summary(value, width))
    elif kind != "cpu" and any(node["kind"] == "gpu" for node in value["nodes"]):
        if details:
            blocks.extend((_gpu_nodes(value, width), Text("GPU: Free/Total"), gpu_legend(), Text("")))
        blocks.append(_summary(value, "gpu", width))
    if value["nodes"] and kind != "gpu" and (kind != "all" or details):
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
