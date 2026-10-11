"""Rich allocation maps over the common local/gateway node DTO."""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from rich import box
from rich.columns import Columns
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.panel import Panel
from rich.table import Table
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


def socket_panel(socket: int, *, cores: int, threads: int, occupied: set[int], chinese: bool,
                 width: int, digits: int) -> Panel:
    start, stop = socket * cores * threads, (socket + 1) * cores * threads
    tiles = []
    for core in range(cores):
        tile = Text(("核 " if chinese else "Core ") + str(core) + "\n")
        for index in range(start + core * threads, start + (core + 1) * threads):
            if index != start + core * threads:
                tile.append(" ")
            tile.append(f"{'*' if index in occupied else ' '}{index:>{digits}}",
                        style=SELECTED if index in occupied else "default")
        tiles.append(tile)
    active = any(start <= index < stop for index in occupied)
    tile_width = max((4 if chinese else 5) + len(str(cores - 1)), threads * (digits + 2) - 1)
    columns = next(count for count in (4, 2, 1) if count * (tile_width + 1) <= width - 3 or count == 1)
    grid = Table.grid(padding=(1, 1))
    for _ in range(columns):
        grid.add_column(width=tile_width)
    for start in range(0, len(tiles), columns):
        grid.add_row(*tiles[start:start + columns])
    return Panel(grid, title=("CPU 插槽 " if chinese else "CPU socket ") + str(socket), width=width,
                 title_align="left", border_style=ALLOCATED if active else "default", box=box.ROUNDED, padding=(0, 1))


def gpu_grid(slots, occupied: set[int], *, width: int) -> Table:
    grid = Table(show_header=False, box=box.SQUARE, show_lines=True, padding=(0, 1))
    cells = [Text(f"{'*' if index in occupied else ' '}{index:>2}",
                  style=SELECTED if index in occupied else "default") for index in slots]
    columns = 8 if width >= 64 else 4
    for start in range(0, len(cells), columns):
        grid.add_row(*cells[start:start + columns])
    return grid


@dataclass(frozen=True)
class AllocationView:
    value: dict
    language: str

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield _allocation_view(self.value, language=self.language, width=options.max_width)


def allocation_view(value: dict, *, language: str = "zh-CN") -> AllocationView:
    return AllocationView(value, language)


def _allocation_view(value: dict, *, language: str, width: int) -> Group:
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
            blocks.append(gpu_grid(slots, occupied, width=width))
        cpu_ids, topology = node.get("cpu_ids"), node.get("cpu_topology")
        if cpu_ids is None:
            blocks.append(Text("CPU 编号未知" if chinese else "CPU IDs unknown", style=UNKNOWN))
        elif topology is None or topology["sockets"] > 32 or topology["cores_per_socket"] > 256 or cpu_cells > 8192:
            blocks.append(Text("CPU  " + ranges(cpu_ids), style="bold"))
        else:
            blocks.extend((Text(""), Text("CPU  " + ranges(cpu_ids), style="bold")))
            cores, threads = topology["cores_per_socket"], topology["threads_per_core"]
            occupied = set(cpu_ids)
            digits = len(str(topology["sockets"] * cores * threads - 1))
            panel_width = (width - 2) // 2 if width >= 76 else width
            blocks.append(Columns([socket_panel(socket, cores=cores, threads=threads, occupied=occupied,
                                                chinese=chinese, width=panel_width, digits=digits)
                                   for socket in range(topology["sockets"])], padding=(1, 2), equal=True))
    blocks.extend((Text(""), Text("* 本作业分配 · CPU 按插槽 / 核分组，数字为 Slurm CPU ID" if chinese else
        "* Allocated to this job · CPU grouped by socket / core, numbers are Slurm CPU IDs")))
    return Group(*blocks)


def render_allocation(value: dict, *, width: int = 100, color: bool = False) -> str:
    output = StringIO()
    Console(file=output, width=max(40, width), force_terminal=color, color_system="standard" if color else None,
            markup=False, highlight=False).print(allocation_view(value))
    return output.getvalue()
