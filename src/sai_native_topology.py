"""Shared read-only hardware interconnect facts. No capture parsers or UI code.

The operator records native hardware observations once. Readers join only the
allocated nodes; live job allocation remains owned by Slurm.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "node.interconnect/v1"
DEFAULT_ROOT = "/opt/sai/runtime/topology"
MAX_BYTES = 512 * 1024
MAX_CPU_IDS = 65536
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_PATH = re.compile(r"NV[1-9][0-9]{0,2}|PIX|PXB|PHB|NODE|SYS")


def _number(value, maximum=65535):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid topology number")
    return value


def _ids(value, maximum=65535):
    if not isinstance(value, list) or len(value) > 65536:
        raise ValueError("invalid topology IDs")
    result = [_number(item, maximum) for item in value]
    if result != sorted(set(result)):
        raise ValueError("duplicate or unordered topology IDs")
    return result


def _time(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value) is None:
        raise ValueError("invalid topology time")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def normalize_interconnect(value):
    """Allowlist the same node DTO in the gateway, CLI and other consumers."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise ValueError("invalid interconnect schema")
    result = {"schema_version": SCHEMA}
    for key in ("node", "cluster"):
        item = value.get(key)
        if not isinstance(item, str) or _NAME.fullmatch(item) is None:
            raise ValueError("invalid topology binding")
        result[key] = item
    start, end = _time(value.get("observed_at")), _time(value.get("expires_at"))
    if start >= end:
        raise ValueError("invalid topology observation interval")
    result.update(observed_at=value["observed_at"], expires_at=value["expires_at"],
                  boot_time=_number(value.get("boot_time"), 2**63 - 1),
                  slurmd_start_time=_number(value.get("slurmd_start_time"), 2**63 - 1))
    if not result["boot_time"] or not result["slurmd_start_time"]:
        raise ValueError("missing node generation")
    dimensions = value.get("cpu_topology")
    if not isinstance(dimensions, dict):
        raise ValueError("missing scheduler dimensions")
    result["cpu_topology"] = {key: _number(dimensions.get(key)) for key in
                              ("sockets", "cores_per_socket", "threads_per_core")}
    total = 1
    for number in result["cpu_topology"].values():
        total *= number
    if not 1 <= total <= 65536:
        raise ValueError("invalid scheduler dimensions")
    domains, gpus, links, nics = (value.get(key) for key in ("numa", "gpus", "links", "nics"))
    if any(not isinstance(rows, list) for rows in (domains, gpus, links, nics)) or not (
        len(domains) <= 256 and len(gpus) <= 64 and len(links) <= 2016 and len(nics) <= 64
    ):
        raise ValueError("interconnect exceeds bounds")
    # Linux IDs may be sparse, and Slurm may use NUMA as sockets.
    # Scheduler counts are not an upper bound on OS/package identifiers.
    result["numa"] = [{"id": _number(row["id"]), "packages": _ids(row["packages"]),
                       "linux_cpu_ids": _ids(row["linux_cpu_ids"])} for row in domains]
    domain_ids = {row["id"] for row in result["numa"]}
    if len(domain_ids) != len(domains):
        raise ValueError("duplicate NUMA domain")
    seen_cpus = set()
    for row in result["numa"]:
        overlap = seen_cpus.intersection(row["linux_cpu_ids"])
        if overlap:
            raise ValueError("NUMA CPU domains overlap")
        seen_cpus.update(row["linux_cpu_ids"])
    mapping = value.get("cpu_mapping")
    if mapping is not None:
        if not isinstance(mapping, dict):
            raise ValueError("invalid CPU mapping")
        mapped = mapping.get("slurm_to_linux")
        if not isinstance(mapped, list) or len(mapped) != total:
            raise ValueError("incomplete CPU mapping")
        mapped = [_number(cpu) for cpu in mapped]
        if len(set(mapped)) != total or not set(mapped).issubset(seen_cpus):
            raise ValueError("CPU mapping is outside Linux topology")
        if not start <= _time(mapping.get("observed_at")) < end:
            raise ValueError("CPU mapping observation is outside record interval")
        result["cpu_mapping"] = {"observed_at": mapping["observed_at"], "slurm_to_linux": mapped}
    result["gpus"] = []
    for row in gpus:
        index = _number(row["index"], 63)
        numa = None if row["numa"] is None else _number(row["numa"])
        cpus = None if row["cpu_ids"] is None else _ids(row["cpu_ids"], total - 1)
        if numa is not None and numa not in domain_ids:
            raise ValueError("GPU NUMA domain absent")
        path = row.get("pcie_path")
        if path is not None and (not isinstance(path, list) or not 1 <= len(path) <= 32 or
                any(not isinstance(ref, str) or re.fullmatch(r"(?:root|bridge)-[0-9]{1,4}", ref) is None for ref in path) or
                not path[0].startswith("root-") or any(not ref.startswith("bridge-") for ref in path[1:]) or len(set(path)) != len(path)):
            raise ValueError("invalid PCIe path")
        result["gpus"].append({"index": index, "numa": numa, "cpu_ids": cpus, "pcie_path": path})
    gpu_ids = {row["index"] for row in result["gpus"]}
    if gpu_ids != set(range(len(gpus))):
        raise ValueError("incomplete scheduler GPU mapping")
    result["links"], pairs = [], set()
    for row in links:
        a, b = _number(row["a"], 63), _number(row["b"], 63)
        kind = row["kind"]
        if a >= b or a not in gpu_ids or b not in gpu_ids or (a, b) in pairs or not isinstance(kind, str) or not _PATH.fullmatch(kind):
            raise ValueError("invalid GPU path")
        pairs.add((a, b))
        result["links"].append({"a": a, "b": b, "kind": kind})
    if len(pairs) != len(gpus) * (len(gpus) - 1) // 2:
        raise ValueError("incomplete GPU path matrix")
    result["nics"] = []
    nic_ids = set()
    for row in nics:
        index = _number(row["index"], 63)
        if index in nic_ids:
            raise ValueError("duplicate NIC")
        nic_ids.add(index)
        paths, seen = [], set()
        if not isinstance(row["gpu_paths"], list) or len(row["gpu_paths"]) > 64:
            raise ValueError("invalid GPU-NIC paths")
        for path in row["gpu_paths"]:
            gpu, kind = _number(path["gpu"], 63), path["kind"]
            if gpu not in gpu_ids or gpu in seen or not isinstance(kind, str) or not _PATH.fullmatch(kind):
                raise ValueError("invalid GPU-NIC path")
            seen.add(gpu)
            paths.append({"gpu": gpu, "kind": kind})
        peer = row["peer"]
        if peer is not None and (not isinstance(peer, str) or re.fullmatch(r"endpoint-[0-9a-f]{24}", peer) is None):
            raise ValueError("invalid fabric peer")
        rate = None if row["rate_gbps"] is None else _number(row["rate_gbps"], 100000)
        result["nics"].append({"index": index, "gpu_paths": paths, "peer": peer, "rate_gbps": rate})
    edges = value.get("fabric_links", [])
    if not isinstance(edges, list) or len(edges) > 4096:
        raise ValueError("fabric links exceed bounds")
    result["fabric_links"], seen = [], set()
    for row in edges:
        a, b = row["a"], row["b"]
        if (any(not isinstance(ref, str) or re.fullmatch(r"endpoint-[0-9a-f]{24}", ref) is None for ref in (a, b))
                or a >= b or (a, b) in seen or row["kind"] != "infiniband"):
            raise ValueError("invalid fabric connection")
        seen.add((a, b))
        result["fabric_links"].append({"a": a, "b": b, "kind": "infiniband"})
    return result


def job_cpu_locality(record, cpu_ids):
    """Project allocation onto NUMA using only the recorded native CPU map."""
    mapping = record.get("cpu_mapping")
    if mapping is None or cpu_ids is None:
        return None
    cpus = _ids(cpu_ids, len(mapping["slurm_to_linux"]) - 1)
    machine = {mapping["slurm_to_linux"][cpu] for cpu in cpus}
    return {row["id"]: sorted(machine.intersection(row["linux_cpu_ids"])) for row in record["numa"]}


def read_interconnect(name, *, cluster, dimensions, gpu_total, root=DEFAULT_ROOT, now=None, trusted_uid=0):
    """Only root-published native mapping assets, without business config/auth."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("invalid topology node")
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "not_recorded"}
    try:
        info = os.fstat(directory)
        if info.st_uid != trusted_uid or info.st_mode & 0o022:
            raise ValueError("unsafe topology directory")
        try:
            fd = os.open(name + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return {"status": "unavailable", "reason": "not_recorded"}
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != trusted_uid or info.st_mode & 0o022 or info.st_size > MAX_BYTES:
                raise ValueError("unsafe topology file")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("topology file exceeds bound")
        value = normalize_interconnect(json.loads(raw))
    finally:
        os.close(directory)
    current = now or datetime.now(timezone.utc)
    if value["node"] != name or value["cluster"] != cluster:
        raise ValueError("topology identity differs")
    newest = value.get("cpu_mapping", {}).get("observed_at", value["observed_at"])
    if not _time(newest) <= current < _time(value["expires_at"]):
        return {"status": "unavailable", "reason": "expired"}
    if value["cpu_topology"] != dimensions or len(value["gpus"]) != gpu_total:
        return {"status": "unavailable", "reason": "configuration_changed"}
    return {"status": "recorded", "value": value}


def same_node_generation(expected, observed):
    """SlurmdStartTime is stable; BootTime is recomputed from reported uptime."""
    starts = []
    for row in (expected, observed):
        if not isinstance(row, dict):
            return False
        value = row.get("slurmd_start_time")
        if isinstance(value, dict):
            value = value.get("number") if value.get("set") is True and value.get("infinite") is False else None
        if type(value) is not int or not 0 < value <= 2**63 - 1:
            return False
        starts.append(value)
    return starts[0] == starts[1]


def join_interconnect(allocation, *, cluster, read_node_state, root=DEFAULT_ROOT, clock=None, trusted_uid=0):
    """Same bounded optional layer for native callers and authorized gateways."""
    nodes = allocation["nodes"] or []
    clock = clock or (lambda: datetime.now(timezone.utc))
    records, size = [], 0
    for node in nodes:
        if len(nodes) > 64:
            record = {"status": "unavailable", "reason": "node_limit"}
        elif node.get("cpu_topology") is None or node.get("gpu_total") is None:
            record = {"status": "unavailable", "reason": "allocation_dimensions_unknown"}
        else:
            try:
                record = read_interconnect(node["name"], cluster=cluster, dimensions=node["cpu_topology"],
                    gpu_total=node["gpu_total"], root=root, now=clock(), trusted_uid=trusted_uid)
            except (OSError, ValueError, TypeError, KeyError):
                record = {"status": "unavailable", "reason": "record_invalid"}
        size += len(json.dumps(record))
        if size > 2 * MAX_BYTES:
            return {"schema_version": "node-interconnect-join/v1", "nodes": [
                {"node": row["name"], "status": "unavailable", "reason": "size_limit"} for row in nodes]}
        records.append({"node": node["name"], **record})
    available = [row for row in records if row["status"] == "recorded"]
    if available:
        names = [row["node"] for row in available]
        state = read_node_state(names)
        if (not isinstance(state, dict) or state.get("errors") != []
                or state.get("meta", {}).get("slurm", {}).get("cluster") != cluster):
            raise ValueError("native node state unavailable")
        state_nodes = state.get("nodes")
        if not isinstance(state_nodes, list) or len(state_nodes) != len(names):
            raise ValueError("native node state incomplete")
        by_name = {row["name"]: row for row in state_nodes}
        if set(by_name) != set(names):
            raise ValueError("native node state differs")
        for record in available:
            native = by_name[record["node"]]
            if not same_node_generation(record["value"], native):
                record.pop("value")
                record.update(status="unavailable", reason="node_restarted")
        finished = clock()
        for record in available:
            if record["status"] == "recorded" and not _time(record["value"]["observed_at"]) <= finished < _time(record["value"]["expires_at"]):
                record.pop("value")
                record.update(status="unavailable", reason="expired")
    peers = {nic["peer"] for record in records if record["status"] == "recorded" for nic in record["value"]["nics"] if nic["peer"] is not None}
    for record in records:
        if record["status"] == "recorded":
            record["value"]["fabric_links"] = [edge for edge in record["value"]["fabric_links"] if edge["a"] in peers and edge["b"] in peers]
    return {"schema_version": "node-interconnect-join/v1", "nodes": records}


def normalize_join(value, allocation, *, cluster, now=None):
    if not isinstance(value, dict) or value.get("schema_version") != "node-interconnect-join/v1":
        raise ValueError("invalid interconnect join")
    nodes = {node["name"]: node for node in allocation["nodes"] or ()}
    rows = value.get("nodes")
    if not isinstance(rows, list) or len(rows) != len(nodes):
        raise ValueError("interconnect join has wrong nodes")
    clean, seen, size = [], set(), 0
    current = now or datetime.now(timezone.utc)
    published_peers = set()
    for row in rows:
        name = row["node"]
        if name not in nodes or name in seen:
            raise ValueError("interconnect is outside allocation")
        seen.add(name)
        if row["status"] == "unavailable":
            if row["reason"] not in {"not_recorded", "expired", "configuration_changed", "allocation_dimensions_unknown",
                                     "record_invalid", "node_limit", "size_limit", "node_restarted"}:
                raise ValueError("invalid interconnect failure")
            clean.append({"node": name, "status": "unavailable", "reason": row["reason"]})
        elif row["status"] == "recorded":
            node = nodes[name]
            record = normalize_interconnect(row["value"])
            if (record["node"] != name or record["cluster"] != cluster or
                    record["cpu_topology"] != node.get("cpu_topology") or len(record["gpus"]) != node.get("gpu_total")):
                raise ValueError("interconnect binding differs")
            size += len(json.dumps(record))
            if size > 2 * MAX_BYTES:
                raise ValueError("interconnect join exceeds bound")
            published_peers.update(nic["peer"] for nic in record["nics"] if nic["peer"] is not None)
            clean.append({"node": name, "status": "recorded", "value": record})
        else:
            raise ValueError("invalid interconnect status")
    for row in clean:
        if row["status"] == "recorded" and any(edge["a"] not in published_peers or edge["b"] not in published_peers for edge in row["value"]["fabric_links"]):
            raise ValueError("fabric connection is outside the job projection")
        newest = row.get("value", {}).get("cpu_mapping", {}).get("observed_at", row.get("value", {}).get("observed_at"))
        if row["status"] == "recorded" and not _time(newest) <= current < _time(row["value"]["expires_at"]):
            row.pop("value")
            row.update(status="unavailable", reason="expired")
    peers = {nic["peer"] for row in clean if row["status"] == "recorded" for nic in row["value"]["nics"] if nic["peer"] is not None}
    for row in clean:
        if row["status"] == "recorded":
            row["value"]["fabric_links"] = [edge for edge in row["value"]["fabric_links"] if edge["a"] in peers and edge["b"] in peers]
    return {"schema_version": value["schema_version"], "nodes": clean}
