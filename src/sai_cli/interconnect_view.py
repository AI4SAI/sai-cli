"""Rich trees and matrices over shared hardware facts; no native parsing."""
from __future__ import annotations

from collections import defaultdict
from rich import box
from rich.console import Group
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .native_resource_view import ALLOCATED, UNKNOWN


_GPU_PATH_LABELS = {
    "PIX": ("单级 PCIe", "Single PCIe bridge"), "PXB": ("多级 PCIe", "PCIe bridges"),
    "PHB": ("经 CPU 桥", "Host bridge"), "NODE": ("同 NUMA", "Within NUMA"),
    "SYS": ("跨 NUMA", "Across NUMA"),
}


def gpu_label(index: int, occupied: set[int]) -> Text:
    return Text(f"GPU {index}{'*' if index in occupied else ''}",
                style=ALLOCATED if index in occupied else "default")


def nvlink_summary(value: dict, occupied: set[int], *, chinese: bool) -> Group:
    """Collapse only proven complete cliques; rings remain explicit edges."""
    from .allocation_view import ranges
    links = {(row['a'],row['b']):row['kind'] for row in value['links']
             if row['kind'].startswith('NV') and {row['a'], row['b']}.issubset(occupied)}
    remaining = {index for edge in links for index in edge}
    parts = []
    while remaining:
        component, pending = set(), [min(remaining)]
        while pending:
            index = pending.pop()
            if index in component:
                continue
            component.add(index)
            pending.extend(b if a == index else a for a,b in links if index in (a,b) and (b if a == index else a) not in component)
        remaining -= component
        members = sorted(component)
        paths = {kind for (a,b),kind in links.items() if a in component and b in component}
        clique = len(paths) == 1 and all((a,b) in links for a in members for b in members if a < b)
        if clique:
            label = Text('GPU ' + ranges(members), style=ALLOCATED if component.intersection(occupied) else 'default')
            label.append(' ─ NVLink ×' + next(iter(paths))[2:] + (' 全互联' if chinese else ' all-to-all'))
            parts.append(label)
        else:
            for (a,b),kind in links.items():
                if a in component:
                    parts.append(Text(f'GPU {a} ─ {kind} ─ GPU {b}'))
    return Group(*parts)


def node_interconnect(value: dict, *, occupied: set[int],
                      chinese: bool, width: int, expanded: bool = False,
                      cpu_ids: list[int] | None = None) -> Group:
    from .allocation_view import ranges
    from sai_native_topology import job_cpu_locality
    locality = job_cpu_locality(value, cpu_ids)
    groups = defaultdict(list)
    for gpu in value["gpus"]:
        groups[gpu["numa"]].append(gpu)
    tree = Tree(Text("CPU ↔ GPU" if value["gpus"] else "CPU / NUMA", style="bold"), guide_style="dim")
    packages_seen = {}
    for domain in value["numa"]:
        gpus = groups.get(domain["id"], [])
        local = sorted({cpu for gpu in gpus for cpu in gpu["cpu_ids"] or ()})
        packages = tuple(domain["packages"])
        if packages not in packages_seen:
            packages_seen[packages] = tree.add(Text("CPU " + ranges(list(packages))))
        label = Text(f"NUMA {domain['id']}")
        assigned = None if locality is None else locality[domain["id"]]
        if assigned:
            label.append(f" · {len(assigned)}/{len(domain['linux_cpu_ids'])} CPU*", style=ALLOCATED)
        elif not gpus:
            label.append(f" · {len(domain['linux_cpu_ids'])} CPU", style="dim" if locality is not None else "default")
        devices = Text()
        if gpus:
            devices.append("PCIe → GPU" if all(gpu.get("pcie_path") for gpu in gpus) else "GPU")
            ids = [gpu['index'] for gpu in gpus]
            if not occupied.intersection(ids):
                devices.append(' ' + ranges(ids))
            else:
                for index in ids:
                    devices.append(f" {index}{'*' if index in occupied else ''}", style=ALLOCATED if index in occupied else "default")
            if width >= 64:
                label.append(" ─ ")
                label.append_text(devices)
        branch = packages_seen[packages].add(label)
        if gpus and width < 64:
            branch.add(devices)
        if expanded and local:
            branch.add(Text(("Slurm 亲和 CPU  " if chinese else "Slurm affinity CPUs  ") + ranges(local)))
        if expanded and assigned:
            branch.add(Text("Linux CPU  " + ranges(assigned), style=ALLOCATED))
        elif expanded and not gpus:
            branch.add(Text("Linux CPU  " + ranges(domain["linux_cpu_ids"])))
        if expanded:
            branches = {}
            for gpu in gpus:
                parent = branch
                for ref in gpu.get("pcie_path") or ():
                    if ref not in branches:
                        name = ("PCIe 根 " if chinese else "PCIe root ") if ref.startswith("root-") else ("PCIe 桥 " if chinese else "PCIe bridge ")
                        branches[ref] = parent.add(Text(name + ref.split('-')[1]))
                    parent = branches[ref]
                if gpu.get("pcie_path"):
                    parent.add(gpu_label(gpu["index"], occupied))
    if groups.get(None):
        branch = tree.add(Text("CPU 亲和未知" if chinese else "CPU affinity unknown", style=UNKNOWN))
        for gpu in groups[None]:
            branch.add(gpu_label(gpu["index"], occupied))
    blocks = [tree]
    if locality is None and cpu_ids:
        blocks.append(Text("CPU 落点未记录" if chinese else "CPU locality not recorded", style=UNKNOWN))
    selected_gpus = sorted(occupied.intersection(gpu["index"] for gpu in value["gpus"]))
    # Small default matrix answers how THIS job's GPUs connect. Expanded view
    # exposes the complete matrix in column blocks, keeping terminal width.
    indices = [gpu["index"] for gpu in value["gpus"]] if expanded else selected_gpus
    if len(indices) > 8 and not expanded:
        blocks.extend((Text(''), nvlink_summary(value, occupied, chinese=chinese)))
        blocks.append(Text("按 i 查看卡间连接" if chinese else "Press i for GPU paths", style="dim"))
    elif len(indices) > 1:
        paths = {(row["a"], row["b"]): row["kind"] for row in value["links"]}
        if len(indices) == 2 and not expanded:
            a,b = indices
            kind = paths[a,b]
            route = 'NVLink ×' + kind[2:] if kind.startswith('NV') else _GPU_PATH_LABELS[kind][0 if chinese else 1]
            line = gpu_label(a,occupied)
            line.append(' ── ' + route + ' ── ',style='cyan')
            line.append_text(gpu_label(b,occupied))
            return Group(*blocks, Text(''), line)
        count = max(2, min(8, (width - 8) // 6))
        for offset in range(0, len(indices), count):
            columns = indices[offset:offset + count]
            matrix = Table(box=box.SIMPLE_HEAD, padding=(0, 1), pad_edge=False, show_edge=False)
            matrix.add_column("GPU")
            for index in columns:
                matrix.add_column(str(index), justify="center")
            for index in indices:
                cells = []
                for other in columns:
                    kind = "·" if index == other else paths[tuple(sorted((index, other)))]
                    cells.append(Text(kind, style="cyan" if kind.startswith("NV") else "default"))
                matrix.add_row(Text(f"{index}{'*' if index in occupied else ''}", style=ALLOCATED if index in occupied else "default"), *cells)
            blocks.extend((Text(""), matrix))
        kinds = {paths[a, b] for a in indices for b in indices if a < b}
        legend = (["NV#：NVLink 条数" if chinese else "NV#: NVLink count"]
                  if any(kind.startswith("NV") for kind in kinds) else [])
        legend.extend(kind + ("：" if chinese else ": ") + labels[0 if chinese else 1]
                      for kind, labels in _GPU_PATH_LABELS.items() if kind in kinds)
        blocks.append(Text(" · ".join(legend), style="dim"))
    if expanded:
        blocks.append(Text(("硬件记录 " if chinese else "Hardware recorded ") + value["observed_at"], style="dim"))
    return Group(*blocks)


def fabric_view(nodes: list[dict], records: dict[str, dict], *, chinese: bool) -> Group:
    peers = defaultdict(list)
    for node in nodes:
        record = records.get(node["name"], {})
        for nic in record.get("nics", ()):
            if nic["peer"] is not None:
                peers[nic["peer"]].append((node["name"], nic["index"], nic["rate_gbps"]))
    if not peers:
        return Group(Text("节点互联未记录" if chinese else "Node links not recorded", style=UNKNOWN))
    tree = Tree(Text("节点互联" if chinese else "Node links", style="bold"), guide_style="dim")
    labels = {peer: index for index, peer in enumerate(peers, 1)}
    for peer, members in peers.items():
        index = labels[peer]
        point = tree.add(Text(("连接点 " if chinese else "Junction ") + str(index)))
        for name, nic, rate in members:
            label = f"{name} ─ NIC {nic}"
            if rate is not None:
                label += f" · {rate} Gb/s"
            point.add(Text(label))
    edges = {tuple(sorted((edge["a"], edge["b"]))) for record in records.values()
             for edge in record.get("fabric_links", ()) if edge["a"] in peers and edge["b"] in peers}
    connections = []
    for a, b in sorted(edges):
        label = "连接点" if chinese else "Junction"
        connections.append(Text(f"{label} {labels[a]} ── IB ── {label} {labels[b]}", style="cyan"))
    if len(peers) > 1 and not connections:
        connections.append(Text("连接点之间的路径未记录" if chinese else "Paths between junctions not recorded", style=UNKNOWN))
    return Group(tree, *connections)
