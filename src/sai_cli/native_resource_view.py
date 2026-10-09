"""Traditional GPU and CPU helper tables over one native observation."""
from __future__ import annotations

from decimal import Decimal
from textwrap import wrap
from typing import Any

from .local_resources import LocalResources, _available, _ready
from .render import format_decimal
from .native_display import allocation_bar, cell_width, clip, paint, quantity, row


def _gib(value: int | None) -> str:
    return "?" if value is None else format_decimal(str(Decimal(value) / 1024), 2)


def _state(node: dict[str, Any]) -> str:
    names = {"ALLOCATED": "ALLOC", "COMPLETING": "COMP", "NOT_RESPONDING": "NO_RESP", "MAINTENANCE": "MAINT"}
    return "+".join(names.get(state, state) for state in node["states"]) or "UNKNOWN"


def _state_role(node: dict[str, Any], ready: bool | None) -> str:
    if ready is False:
        return "blocked"
    if ready is None:
        return "unknown"
    return "free" if "IDLE" in node["states"] else "allocated"


def _qos(part: dict[str, Any]) -> str:
    qos = part["qos"]
    result = qos["allowed"] if qos["allowed"] is not None else "?"
    if qos["deny"]:
        result += " (deny: " + qos["deny"] + ")"
    return result or "ALL"


def _gpu_nodes(value: dict[str, Any], *, width: int, color: bool) -> list[str]:
    narrow = width < 90
    widths = [12, 16, 9, 7]
    matrix_cells = min(16, max(4, (width - sum(widths) - 8) // 3))
    table_width = min(width, sum(widths) + 8 + max(14, matrix_cells * 3))
    header = row(("NodeName", "Status", "Partition", "GPU", "GPU Allocation"), [*widths, 14])
    lines = ["=" * table_width] if not narrow else []
    if not narrow:
        lines.extend((header, "-" * table_width))
    for part in value["partitions"]:
        members = [node for node in value["nodes"] if part["name"] in node["partitions"] and node["kind"] == "gpu"]
        if not members:
            continue
        if narrow:
            lines.extend((paint(part["name"], "heading", color),
                          row(("NodeName", "Status", "GPU"), (12, 16, 7)), "-" * min(width, 39)))
        for node in members:
            ready = _ready(node, [part])
            total, allocated = node["gpu"]["configured_units"], node["gpu"]["allocated_units"]
            free = _available(node["gpu"]["unallocated_units"], ready)
            state = paint(clip(_state(node), 16), _state_role(node, ready), color)
            amount = paint(f"{quantity(free)}/{quantity(total)}", "free" if free else _state_role(node, ready), color)
            matrix = allocation_bar(total, allocated, free, cells=max(1, (width - 2) // 3) if narrow else matrix_cells,
                                    color=color, unit_cells=True)
            name = clip(node["name"], 12)
            if narrow:
                lines.extend((row((name, state, amount), (12, 16, 7)), "  " + matrix))
            else:
                lines.append(row((name, state, clip(part["name"], 9), amount, matrix), [*widths, 14]))
    if lines:
        lines.extend(("-" * table_width,
                      paint("[_] Free", "free", color) + "  " + paint("[#] Alloc", "allocated", color) +
                      "  " + paint("[x] Blocked", "blocked", color), "GPU: Free/Total"))
    return lines


def _cpu_nodes(value: dict[str, Any], *, width: int, color: bool) -> list[str]:
    if width >= 150:
        widths = (12, 8, 8, 8, 6, 6, 6, 7, 10, 16, 14, max(16, width - 133))
        lines = [row(("", "Scheduled Mem(GiB)", "Scheduled CPUs", "Reported", "Cluster Options"), (12, 28, 22, 37, 28)),
                 row(("NodeName", "total", "alloc", "avail", "total", "alloc", "avail", "LOAD", "Mem_free", "Status", "Partition", "QOS"), widths),
                 "-" * width]
        for part in value["partitions"]:
            for node in value["nodes"]:
                if part["name"] not in node["partitions"] or node["kind"] == "gpu":
                    continue
                cpu, mem, reported = node["cpu"], node["memory"], node["reported"]
                load = "?" if reported["cpu_load_hundredths"] is None else f"{reported['cpu_load_hundredths'] / 100:.2f}"
                lines.append(row((node["name"], _gib(mem["effective_mib"]), _gib(mem["allocated_mib"]), _gib(mem["unallocated_mib"]),
                                  quantity(cpu["effective_total"]), quantity(cpu["allocated"]), quantity(cpu["effective_idle"]), load,
                                  _gib(reported["free_memory_mib"]), paint(_state(node), _state_role(node, _ready(node, [part])), color),
                                  part["name"], _qos(part)), widths))
        return lines
    lines = []
    for part in value["partitions"]:
        members = [node for node in value["nodes"] if part["name"] in node["partitions"] and node["kind"] != "gpu"]
        if not members:
            continue
        if lines:
            lines.append("")
        lines.append(paint(part["name"], "heading", color))
        if width >= 110:
            widths = [12, 8, 8, 8, 6, 6, 6, 7, 10, 16]
            lines.extend((row(("", "Scheduled Mem(GiB)", "Scheduled CPUs", "Reported", ""), (12, 28, 22, 19, 16)),
                          row(("NodeName", "total", "alloc", "avail", "total", "alloc", "avail", "LOAD", "Mem_free", "Status"), widths),
                          "-" * (sum(widths) + 18)))
            for node in members:
                cpu, mem, reported = node["cpu"], node["memory"], node["reported"]
                load = "?" if reported["cpu_load_hundredths"] is None else f"{reported['cpu_load_hundredths'] / 100:.2f}"
                lines.append(row((node["name"], _gib(mem["effective_mib"]), _gib(mem["allocated_mib"]), _gib(mem["unallocated_mib"]),
                                  quantity(cpu["effective_total"]), quantity(cpu["allocated"]), quantity(cpu["effective_idle"]), load,
                                  _gib(reported["free_memory_mib"]), paint(_state(node), _state_role(node, _ready(node, [part])), color)), widths))
        else:
            lines.extend((row(("NodeName", "Status", "CPU A/T"), (12, 16, 7)), "-" * min(width, 39)))
            for node in members:
                cpu, mem, reported = node["cpu"], node["memory"], node["reported"]
                state = paint(clip(_state(node), 16), _state_role(node, _ready(node, [part])), color)
                lines.append(row((clip(node["name"], 12), state, f"{quantity(cpu['allocated'])}/{quantity(cpu['effective_total'])}"), (12, 16, 7)))
                lines.extend(wrap(f"  Mem GiB total/alloc/avail: {_gib(mem['effective_mib'])}/{_gib(mem['allocated_mib'])}/{_gib(mem['unallocated_mib'])}", width=width))
                load = "?" if reported["cpu_load_hundredths"] is None else f"{reported['cpu_load_hundredths'] / 100:.2f}"
                lines.extend(wrap(f"  LOAD {load}  Mem_free {_gib(reported['free_memory_mib'])} GiB", width=width))
        lines.extend(wrap("Allowed QOS: " + _qos(part), width=width, break_on_hyphens=False))
    return lines


def _partition_summary(value: dict[str, Any], *, width: int, color: bool, family: str) -> list[str]:
    gpu = family == "gpu"
    narrow = width < 100
    widths = [max(9, min(18, max((len(part["name"]) for part in value["partitions"]), default=9))), 6, 6, 7, 19, 8]
    headings = ("Partition", "TotGPU" if gpu else "TotCPU", "Avail", "Blocked", "Allocated", "Max/node")
    title = "::: Partition Summary :::" if value["filters"]["kind"] != "all" else f"::: {family.upper()} Partition Summary :::"
    lines = [paint(title, "heading", color)]
    if not narrow:
        lines.extend(("=" * min(width, 140), row(headings, widths) + "  Allowed QOS", "-" * min(width, 140)))
    for part in [*value["partitions"], {"name": "GLOBAL", "summary": value["summary"]}]:
        resource = part["summary"][family]
        total, allocated, free = resource["capacity"], resource["allocated"], resource["free_on_ready_nodes"]
        if total == 0:
            continue
        percent = "    ?" if total is None or allocated is None or total == 0 else f"{allocated / total * 100:5.1f}"
        bar = allocation_bar(total, allocated, free, cells=10, color=color)
        available = paint(quantity(free), "free", color) if free else quantity(free)
        name = part["name"]
        if name == "GLOBAL":
            lines.append("-" * min(width, 140))
        if narrow:
            lines.append(paint(name, "bold" if name == "GLOBAL" else "heading", color))
            lines.append(row(("Total", "Avail", "Alloc", "Blocked"), (8, 8, 8, 8)))
            lines.append(row((quantity(total), available, quantity(allocated), quantity(resource["blocked_unallocated"])), (8, 8, 8, 8)))
            lines.append(f"{percent}% {bar}  max/node {quantity(resource['largest_free_on_one_node'])}")
        else:
            cells = (paint(name, "bold", color) if name == "GLOBAL" else name, quantity(total), available,
                     quantity(resource["blocked_unallocated"]), f"{percent}% {bar}", quantity(resource["largest_free_on_one_node"]))
            text = row(cells, widths)
            if name != "GLOBAL":
                prefix = sum(widths) + 12
                qos_lines = wrap(_qos(part), width=max(18, width - prefix), break_on_hyphens=False)
                text = text.ljust(len(text) + max(0, prefix - cell_width(text))) + qos_lines[0]
                lines.append(text)
                lines.extend(" " * prefix + text for text in qos_lines[1:])
            else:
                lines.append(text)
        if not gpu:
            memory = part["summary"]["memory"]
            lines.extend(wrap(f"  Mem GiB: {_gib(memory['free_on_ready_nodes'])} available / {_gib(memory['capacity'])} total", width=width))
        if narrow and name != "GLOBAL":
            lines.extend(wrap("QOS: " + _qos(part), width=width, break_on_hyphens=False))
    lines.append("=" * min(width, 140))
    return lines


def render_local_resources(result: LocalResources, *, details: bool = False, width: int = 120, color: bool = False) -> str:
    value = result.values
    width = max(40, width)
    if not value["nodes"]:
        return "No native nodes matched this query.\n"
    lines = []
    if details:
        if value["filters"]["kind"] != "cpu":
            lines.extend(_gpu_nodes(value, width=width, color=color))
        if value["filters"]["kind"] != "gpu":
            lines.extend(_cpu_nodes(value, width=width, color=color))
        lines.append("")
    families = ("gpu", "cpu") if value["filters"]["kind"] == "all" else (value["filters"]["kind"],)
    for family in families:
        lines.extend(_partition_summary(value, width=width, color=color, family=family))
    lines.extend(wrap("Avail: unallocated on ready nodes. Access and reservations still apply.", width=width))
    if value["filters"]["kind"] != "cpu":
        lines.extend(wrap("GPU cells show allocation counts, not device positions or measured utilization.", width=width))
    if value["unclassified_nodes"]:
        lines.extend(wrap(f"GPU configuration unknown on {value['unclassified_nodes']} node(s); inspect --kind all.", width=width))
    return "\n".join(lines) + "\n"
