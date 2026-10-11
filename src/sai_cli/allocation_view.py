"""Rich allocation maps over the common local/gateway node DTO."""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.text import Text
from rich.table import Table
from .native_resource_view import ALLOCATED, UNKNOWN, _gib


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


@dataclass(frozen=True)
class AllocationView:
    value: dict
    language: str
    expanded: bool = False

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield _allocation_view(self.value, language=self.language, width=options.max_width, expanded=self.expanded)


def allocation_view(value: dict, *, language: str = "zh-CN", expanded: bool = False) -> AllocationView:
    return AllocationView(value, language, expanded)


def _allocation_view(value: dict, *, language: str, width: int, expanded: bool = False) -> Group:
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
    from .interconnect_view import node_interconnect, fabric_view
    failures = {row["node"]: row["reason"] for row in value.get("interconnect", {}).get("nodes", ())
                if row.get("status") == "unavailable"}
    records = {row["node"]: row["value"] for row in value.get("interconnect", {}).get("nodes", ())
               if row.get("status") == "recorded"}
    if len(allocation["nodes"]) > 1:
        blocks.extend((Text(""), fabric_view(allocation["nodes"], records, chinese=chinese)))

    for node in allocation["nodes"]:
        blocks.extend((Text(""), Text(f"{node['name']}  ·  {node['cpus']} CPU  ·  {_gib(node['memory_mib'])} GiB", style="bold")))
        if node["gres"] is None and node.get("gpu_total") != 0:
            blocks.append(Text("GPU IDX  ?", style=UNKNOWN))
        occupied = set()
        for resource in node["gres"] or ():
            title = resource["name"].upper()
            model = "  " + resource["type"] if resource["type"] else ""
            indices = resource["indices"]
            if indices is None:
                blocks.append(Text(f"{title}  ×{resource['count']}{model}  ·  " + ("编号未知" if chinese else "IDs unknown")))
                continue
            selected_ids = ", ".join(map(str, indices)) if len(indices) <= 8 else ranges(indices)
            blocks.append(Text(f"{title}  " + selected_ids + model, style="bold"))
            if resource["name"] == "gpu":
                occupied.update(indices)
        cpu_ids, topology = node.get("cpu_ids"), node.get("cpu_topology")
        if cpu_ids is None:
            blocks.append(Text("CPU 编号未知" if chinese else "CPU IDs unknown", style=UNKNOWN))
        else:
            blocks.append(Text("CPU  " + ranges(cpu_ids), style="bold"))
        record = records.get(node["name"])
        if record is not None:
            blocks.append(node_interconnect(record, cpu_ids=cpu_ids, occupied=occupied,
                chinese=chinese, width=width, expanded=expanded))
        else:
            if topology and cpu_ids:
                group_size = topology["cores_per_socket"] * topology["threads_per_core"]
                groups = sorted({index // group_size for index in cpu_ids})
                summary = Table.grid(padding=(0, 2))
                for socket in groups:
                    assigned = [index for index in cpu_ids if index // group_size == socket]
                    summary.add_row(Text(("Slurm 组 " if chinese else "Slurm group ") + str(socket)),
                        Text(f"{len(assigned)}/{group_size} CPU", style=ALLOCATED),
                        Text(ranges(assigned)) if expanded else Text(""))
                blocks.append(summary)
            reasons = {"expired": ("硬件记录已过期", "Hardware record expired"),
                       "node_restarted": ("节点已重启，映射待更新", "Node restarted; mapping needs refresh"),
                       "configuration_changed": ("硬件配置已变更", "Hardware configuration changed"),
                       "record_invalid": ("硬件记录暂不可用", "Hardware record unavailable")}
            message = reasons.get(failures.get(node["name"]), ("硬件互联未记录", "Hardware links not recorded"))
            blocks.append(Text(message[0 if chinese else 1], style=UNKNOWN))
    if records:
        blocks.extend((Text(""), Text("* 本作业分配" if chinese else "* Allocated to this job", style="dim")))
    return Group(*blocks)


def render_allocation(value: dict, *, width: int = 100, color: bool = False, expanded: bool = False) -> str:
    output = StringIO()
    Console(file=output, width=max(40, width), force_terminal=color, color_system="standard" if color else None,
            markup=False, highlight=False).print(allocation_view(value, expanded=expanded))
    return output.getvalue()
