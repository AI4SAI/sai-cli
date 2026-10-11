"""Selectable native node rows reuse the alias renderers and one observation."""
from __future__ import annotations

from decimal import Decimal

from rich.console import Group
from rich.table import Table
from rich.text import Text

from .local_resources import _available, _ready
from .native_resource_view import _allocation, _gib, _gpu_matrix, _number, _state, _qos
from .render import format_decimal


def node_cells(node: dict, partitions: list[dict], *, kind: str, width: int) -> list:
    ready = _ready(node, [part for part in partitions if part["name"] in node["partitions"]])
    cells = [Text(node["name"]), _state(node, ready)]
    if kind == "gpu":
        gpu = node["gpu"]
        cells.extend((Text(f"{_number(_available(gpu['unallocated_units'], ready))}/{_number(gpu['configured_units'])}"),
                      _gpu_matrix(node, ready)))
    else:
        cpu, memory = node["cpu"], node["memory"]
        bars = 5 if width >= 80 else 0
        cells.extend((_allocation(cpu["allocated"], cpu["effective_total"], bars=bars, ready=ready),
                      _allocation(memory["allocated_mib"], memory["effective_mib"], memory=True, bars=bars, ready=ready)))
    return cells


def compact_summary(value: dict, kind: str, language: str) -> Group:
    rows = []
    for part in [*value["partitions"], {"name": "GLOBAL", "summary": value["summary"]}]:
        capacity = part["summary"][kind]
        rows.append(Text(f"{part['name']}  {_number(capacity['free_on_ready_nodes'])}/{_number(capacity['capacity'])} " +
                         ("空闲" if language == "zh-CN" else "free")))
    return Group(*rows)


def node_detail(node: dict, partitions: list[dict], *, language: str, width: int = 100) -> Group:
    chinese = language == "zh-CN"
    parts = [part for part in partitions if part["name"] in node["partitions"]]
    ready = _ready(node, parts)
    title = Text(node["name"] + "  ·  ", style="bold")
    title.append_text(_state(node, ready))
    grid = Table.grid(padding=(0, 2))
    grid.add_row("分区" if chinese else "Partitions", Text(", ".join(node["partitions"])))
    cpu, memory, reported = node["cpu"], node["memory"], node["reported"]
    bars = 5 if width >= 64 else 0
    grid.add_row("CPU 分配" if chinese else "CPU allocated",
                 _allocation(cpu["allocated"], cpu["effective_total"], bars=bars, ready=ready))
    grid.add_row("内存分配 GiB" if chinese else "Memory allocated GiB",
                 _allocation(memory["allocated_mib"], memory["effective_mib"], memory=True, bars=bars, ready=ready))
    topology = node.get("cpu_topology")
    if topology is not None:
        dimensions = (f"{topology['sockets']} 插槽 × {topology['cores_per_socket']} 核 × {topology['threads_per_core']} 线程"
                      if chinese else f"{topology['sockets']} sockets × {topology['cores_per_socket']} cores × {topology['threads_per_core']} threads")
        grid.add_row("CPU 结构" if chinese else "CPU layout", dimensions)
    load = reported["cpu_load_hundredths"]
    grid.add_row("系统负载" if chinese else "System load", "?" if load is None else format_decimal(str(Decimal(load) / 100), 1, trim=True))
    grid.add_row("系统空闲 GiB" if chinese else "System free GiB", _gib(reported["free_memory_mib"]))
    for part in parts:
        grid.add_row(Text(part["name"] + " QOS"), Text(_qos(part)))
    blocks = [title, grid]
    if node["kind"] == "gpu":
        from .allocation_view import ranges
        indices = node["gpu"]["allocated_indices"]
        blocks.extend((Text(("GPU 已分配编号  " if chinese else "Allocated GPU indices  ") +
                            ("?" if indices is None else ranges(indices)), style="bold"),
                       _gpu_matrix(node, ready, numbered=True),
                       Text("蓝色：已分配  绿色：空闲  红色：不可用" if chinese else
                            "Blue: allocated  Green: idle  Red: unavailable", style="dim")))
    return Group(*blocks)
