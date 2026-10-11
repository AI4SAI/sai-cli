"""Rich allocation maps over the common local/gateway node DTO."""
from __future__ import annotations

from io import StringIO
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from .native_resource_view import ALLOCATED, UNKNOWN, _gib

SELECTED = "bold bright_white on dark_blue"


def ranges(values: list[int]) -> str:
    if not values:
        return "—"
    parts, start, end = [], values[0], values[0]
    for value in values[1:]:
        if value == end + 1:
            end = value
        else:
            parts.append(str(start) if start == end else f"{start}–{end}")
            start = end = value
    parts.append(str(start) if start == end else f"{start}–{end}")
    return ", ".join(parts)


def socket_panel(socket: int, *, cores: int, threads: int, occupied: set[int], chinese: bool) -> Panel:
    start, stop = socket * cores * threads, (socket + 1) * cores * threads
    text = Text()
    first = start
    for index in range(start + 1, stop + 1):
        if index == stop or (index in occupied) != (first in occupied):
            if text:
                text.append("  ")
            label = str(first) if index == first + 1 else f"{first}–{index - 1}"
            text.append(" " + label + " ", style=SELECTED if first in occupied else "white")
            first = index
    active = any(start <= index < stop for index in occupied)
    return Panel(text, title=("CPU 插槽 " if chinese else "CPU socket ") + str(socket),
                 title_align="left", border_style=ALLOCATED if active else "dim", box=box.ROUNDED, padding=(0, 1))


def allocation_view(value: dict, *, language: str = "zh-CN") -> Group:
    chinese = language == "zh-CN"
    job, allocation = value["job"], value["allocation"]
    identity = job["job_id"] + ("_" + job["array_task_id"] if job["array_task_id"] is not None else "")
    blocks = [Text(f"{identity}  {job['name'] or ''}  ·  {job['state']}", style="bold")]
    blocks.append(Text(" · ".join(str(job[key]) for key in ("slurm_account", "partition") if job.get(key))))
    if allocation["status"] != "allocated":
        state = allocation["status"]
        blocks.append(Text(("尚未分配节点" if chinese else "No nodes allocated") if state == "not_allocated" else
                           ("当前分配未知" if chinese else "Allocation unavailable"), style=UNKNOWN))
        if job.get("reason_or_nodelist"):
            blocks.append(Text(job["reason_or_nodelist"]))
        return Group(*blocks)
    cpu_cells = sum((node.get("cpu_topology") or {}).get("sockets", 0) *
                    (node.get("cpu_topology") or {}).get("cores_per_socket", 0) for node in allocation["nodes"])
    gpu_cells = sum((node.get("gpu_total") or len(resource["indices"] or ()))
                    for node in allocation["nodes"] for resource in node["gres"] or ())
    for node in allocation["nodes"]:
        blocks.extend((Text(""), Text(f"{node['name']}  ·  {node['cpus']} CPU  ·  {_gib(node['memory_mib'])} GiB", style="bold")))
        if node["gres"] is None and node.get("gpu_total") != 0:
            blocks.append(Text("GPU IDX  ?", style=UNKNOWN))
        for resource in node["gres"] or ():
            title = resource["name"].upper()
            model = "  " + resource["type"] if resource["type"] else ""
            indices = resource["indices"]
            if indices is None:
                blocks.append(Text(f"{title}  ×{resource['count']}{model}  ·  " + ("编号未知" if chinese else "IDs unknown")))
                continue
            total = node.get("gpu_total") if resource["name"] == "gpu" else None
            slots = range(total) if total is not None and (not indices or indices[-1] < total) else indices
            if len(slots) > 64 or gpu_cells > 2048:
                blocks.append(Text(f"{title}  " + ranges(indices) + model, style="bold"))
                continue
            occupied = set(indices)
            selected_ids = ", ".join(map(str, indices)) if len(indices) <= 8 else ranges(indices)
            blocks.append(Text(f"{title}  " + selected_ids + model, style="bold"))
            blocks.append(Columns([Text(f" {index:^2} ", style=SELECTED if index in occupied else "white")
                                   for index in slots], padding=(0, 1), equal=True))
        cpu_ids, topology = node.get("cpu_ids"), node.get("cpu_topology")
        if cpu_ids is None:
            blocks.append(Text("CPU 编号未知" if chinese else "CPU IDs unknown", style=UNKNOWN))
        elif topology is None or topology["sockets"] > 32 or topology["cores_per_socket"] > 256 or cpu_cells > 8192:
            blocks.append(Text("CPU  " + ranges(cpu_ids), style="bold"))
        else:
            blocks.extend((Text(""), Text("CPU  " + ranges(cpu_ids), style="bold")))
            cores, threads = topology["cores_per_socket"], topology["threads_per_core"]
            occupied = set(cpu_ids)
            blocks.append(Columns([socket_panel(socket, cores=cores, threads=threads, occupied=occupied, chinese=chinese)
                                   for socket in range(topology["sockets"])], width=18, padding=(0, 1), equal=True))
    blocks.extend((Text(""), Text("高亮：本作业分配" if chinese else "Highlighted: allocated to this job", style="dim")))
    return Group(*blocks)


def render_allocation(value: dict, *, width: int = 100, color: bool = False) -> str:
    output = StringIO()
    Console(file=output, width=max(40, width), force_terminal=color, color_system="standard" if color else None,
            markup=False, highlight=False).print(allocation_view(value))
    return output.getvalue()
