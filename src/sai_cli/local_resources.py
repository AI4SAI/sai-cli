"""One native Slurm node observation for GPU/CPU queries and SSH helpers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any, Mapping

from .errors import ConfigError
from .native_process import read_native_json
from .native_values import (invalid_native, local_options, native_environment,
                            native_header, native_number, native_text, native_user)


_BLOCKED = {"DOWN", "DRAIN", "DRAINED", "DRAINING", "FAIL", "FAILING", "MAINTENANCE",
            "NOT_RESPONDING", "NO_RESPOND", "POWER_DOWN", "POWERED_DOWN", "POWERING_DOWN",
            "POWERING_UP", "FUTURE", "INVALID_REG", "UNKNOWN"}
_NOT_REPORTING = {"DOWN", "NOT_RESPONDING", "NO_RESPOND", "POWER_DOWN", "POWERED_DOWN",
                  "POWERING_DOWN", "POWERING_UP", "FUTURE", "UNKNOWN"}
_BASE_UP = {"IDLE", "MIXED", "ALLOCATED", "COMPLETING"}
_GRES = re.compile(r"([^(),]+)(?:\([^()]*\))?(?:,|$)")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid_native()
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 4096:
        raise invalid_native()
    return sorted(set(native_text(item, required=True) for item in value))


def _equal_range(value: object) -> int | None:
    bounds = _object(value)
    low, high = native_number(bounds.get("minimum")), native_number(bounds.get("maximum"))
    if low != high:
        raise invalid_native()
    return low


def _gpu_counts(value: object) -> dict[str | None, int] | None:
    """Read configured/allocated GRES counts; indices are not device identity."""
    if value is None:
        return None
    value = native_text(value)
    if value in {"", "(null)"}:
        return {}
    result: dict[str | None, int] = {}
    offset = 0
    while offset < len(value):
        match = _GRES.match(value, offset)
        if match is None:
            return None
        parts = match[1].split(":")
        if len(parts) not in {2, 3} or not all(parts):
            return None
        if parts[0] == "gpu":
            if len(parts) not in {2, 3} or not parts[-1].isdecimal():
                return None
            kind = parts[1] if len(parts) == 3 else None
            if kind in result:
                return None
            result[kind] = native_number(int(parts[-1]))
        offset = match.end()
    return result


def _gpu_total(values: dict[str | None, int] | None) -> int | None:
    if values is None:
        return None
    # A generic total and typed entries can describe the same units.
    return values[None] if None in values else sum(values.values())


def _remaining(total: int | None, allocated: int | None) -> int | None:
    return None if total is None or allocated is None else max(0, total - allocated)


def _reserved_cpus(value: object) -> int | None:
    """Count the native CPU-ID set without expanding ranges or guessing topology."""
    if value is None:
        return None
    value = native_text(value)
    if value == "":
        return 0
    ranges = []
    for piece in value.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", piece)
        if match is None:
            return None
        first, last = int(match[1]), int(match[2] or match[1])
        if first > last:
            return None
        ranges.append((first, last))
    count, previous = 0, -1
    for first, last in sorted(ranges):
        count += max(0, last - max(first, previous + 1) + 1)
        previous = max(previous, last)
    return native_number(count)


def _node(entry: dict[str, Any]) -> dict[str, Any]:
    names = _strings(_object(entry.get("nodes")).get("nodes"))
    if len(names) != 1:
        raise invalid_native()  # --Node must give per-node facts, not group averages.
    states = _strings(_object(entry.get("node")).get("state"))
    ready = False if _BLOCKED.intersection(states) else True if _BASE_UP.intersection(states) else None
    cpus, memory, gres = (_object(entry.get(key)) for key in ("cpus", "memory", "gres"))
    reserved = _object(entry.get("resource_spec"))
    reserved_cpus = _reserved_cpus(reserved.get("cpus"))
    reserved_mem = native_number(reserved.get("memory"))
    total_cpu = native_number(cpus.get("total"))
    idle_cpu = native_number(cpus.get("idle"))
    configured, allocated = _gpu_counts(gres.get("total")), _gpu_counts(gres.get("used"))
    total_gpu, used_gpu = _gpu_total(configured), _gpu_total(allocated)
    gpu_kind = "unknown" if total_gpu is None else "gpu" if total_gpu else "cpu"
    total_mem = _equal_range(memory)
    allocated_mem = native_number(memory.get("allocated"))
    effective_mem = _remaining(total_mem, reserved_mem)
    load = _equal_range(cpus.get("load"))
    free_mem = _equal_range(memory.get("free"))
    if _NOT_REPORTING.intersection(states) or ready is None:
        load, free_mem = None, None
    elif load in {2**32 - 1, 2**32 - 2}:
        load = None
    return {
        "name": names[0], "states": states, "kind": gpu_kind, "node_ready": ready,
        "gpu": {"configured_units": total_gpu, "allocated_units": used_gpu,
                "unallocated_units": _remaining(total_gpu, used_gpu),
                "types": None if configured is None else sorted(kind for kind in configured if kind is not None)},
        "cpu": {**{key: native_number(cpus.get(key)) for key in ("total", "allocated", "idle", "other")},
                "reserved": reserved_cpus, "effective_total": _remaining(total_cpu, reserved_cpus),
                "effective_idle": _remaining(idle_cpu, reserved_cpus)},
        "memory": {"configured_mib": total_mem, "allocated_mib": allocated_mem,
                   "reserved_mib": reserved_mem, "effective_mib": effective_mem,
                   "unallocated_mib": _remaining(effective_mem, allocated_mem)},
        "reported": {"cpu_load_hundredths": load, "free_memory_mib": free_mem, "sampled_at": None},
    }


def _partition(value: object) -> dict[str, Any]:
    data = _object(value)
    states = _strings(_object(data.get("partition")).get("state"))
    ready = True if states == ["UP"] else False if set(states).intersection({"DOWN", "INACTIVE", "DRAIN"}) else None
    qos = _object(data.get("qos"))
    return {"name": native_text(data.get("name"), required=True), "states": states,
            "partition_ready": ready,
            "qos": {key: native_text(qos.get(key)) for key in ("allowed", "deny", "assigned")}}


def _ready(node: dict[str, Any], partitions: list[dict[str, Any]]) -> bool | None:
    if node["node_ready"] is False:
        return False
    possible = [part["partition_ready"] for part in partitions]
    if possible and all(value is False for value in possible):
        return False
    if node["node_ready"] is True and any(value is True for value in possible):
        return True
    return None


def _sum(values: list[int | None]) -> int | None:
    return None if any(value is None for value in values) else sum(values)


def _max(values: list[int | None]) -> int | None:
    return None if any(value is None for value in values) else max(values, default=0)


def _available(value: int | None, ready: bool | None) -> int | None:
    if ready is False or value == 0:
        return 0
    return value if ready is True else None


def _summary(nodes: list[dict[str, Any]], parts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    readiness = [_ready(node, [parts[name] for name in node["partitions"] if name in parts]) for node in nodes]
    result: dict[str, Any] = {"nodes": len(nodes), "ready_nodes": readiness.count(True),
                              "unknown_state_nodes": readiness.count(None)}
    for family, total, allocated, unallocated in (
        ("gpu", "configured_units", "allocated_units", "unallocated_units"),
        ("cpu", "effective_total", "allocated", "effective_idle"),
        ("memory", "effective_mib", "allocated_mib", "unallocated_mib"),
    ):
        values = [node[family][unallocated] for node in nodes]
        free = [_available(value, ready) for value, ready in zip(values, readiness)]
        unassigned = ([_remaining(node[family][total], node[family][allocated]) for node in nodes]
                      if family == "cpu" else values)
        blocked = [_remaining(value, available) for value, available in zip(unassigned, free)]
        result[family] = {"capacity": _sum([node[family][total] for node in nodes]),
                          "allocated": _sum([node[family][allocated] for node in nodes]),
                          "free_on_ready_nodes": _sum(free), "blocked_unallocated": _sum(blocked),
                          "largest_free_on_one_node": _max(free)}
    return result


@dataclass(frozen=True)
class LocalResources:
    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.values


def read_local_resources(args: argparse.Namespace, *, environ: Mapping[str, str]) -> LocalResources:
    timeout = local_options(args, command="resources local")
    actor = native_user()
    if args.partition_name is not None and args.partition is not None:
        raise ConfigError("choose the positional partition or --partition, not both")
    partition = args.partition_name if args.partition_name is not None else args.partition
    filters = {"partition": partition, "nodes": args.node, "kind": args.kind}
    for value in (partition, args.node):
        if value is not None and (not value.strip() or len(value) > 4096
                                  or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
            raise ConfigError("native filters must be nonempty text without control characters")
    argv = ["sinfo", "--json", "--local", "--Node"]
    if partition is not None:
        argv.append("--partition=" + partition)
    if args.node is not None:
        argv.append("--nodes=" + args.node)
    payload = read_native_json(argv, environ=native_environment(environ, filter_prefix="SINFO_"), timeout=timeout)
    cluster, warnings = native_header(payload)
    rows = payload.get("sinfo")
    if not isinstance(rows, list):
        raise invalid_native()
    nodes: dict[str, dict[str, Any]] = {}
    parts: dict[str, dict[str, Any]] = {}
    memberships: dict[str, set[str]] = {}
    for raw in rows:
        entry = _object(raw)
        node, part = _node(entry), _partition(entry.get("partition"))
        name, part_name = node["name"], part["name"]
        if (name in nodes and nodes[name] != node) or (part_name in parts and parts[part_name] != part):
            raise invalid_native()
        nodes[name], parts[part_name] = node, part
        memberships.setdefault(name, set()).add(part_name)
    unknown = sum(node["kind"] == "unknown" for node in nodes.values())
    selected = []
    for name in sorted(nodes):
        node = nodes[name]
        if args.kind == "all" or node["kind"] == args.kind:
            selected.append({**node, "partitions": sorted(memberships[name])})
    selected_parts = []
    for name in sorted(parts):
        members = [node for node in selected if name in node["partitions"]]
        if members:
            selected_parts.append({**parts[name], "summary": _summary(members, {name: parts[name]})})
    return LocalResources({"schema_version": "native.resources/v1", "source": "sinfo", "authority": "native",
        "observation_kind": "scheduler", "cluster": cluster, "actor": {"user": actor, "uid": os.geteuid()},
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "filters": filters, "nodes": selected, "partitions": selected_parts,
        "summary": _summary(selected, parts), "unclassified_nodes": unknown, "warning_count": warnings})
