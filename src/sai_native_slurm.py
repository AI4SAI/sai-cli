"""Canonical bounded native Slurm allocation and resource projections."""
from __future__ import annotations

import re
from typing import Any


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}")
_SEGMENT = re.compile(r"([^(),:]+(?::[^(),:]+){0,2})\(([^()]*)\)")
_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,18})")
_INDEX_RANGE = re.compile(r"(0|[1-9][0-9]{0,9})(?:-(0|[1-9][0-9]{0,9}))?")
_MAX_COUNT = 2**63 - 1
_MAX_INDEX = 2**31 - 1
MAX_OBSERVATION_GRES_ENTRIES = 4096
MAX_OBSERVATION_GRES_INDICES = 65536


class GresBudgetExceeded(ValueError):
    """The observation cannot publish a complete bounded GRES layer."""


def normalize_gres_observation(value: object) -> list[dict[str, Any]] | None:
    """Validate the public DTO and discard unknown fields at every level."""
    if value is None:
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ValueError("GRES observation is invalid")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or not {"name", "type", "count", "indices"} <= item.keys():
            raise ValueError("GRES observation fields are invalid")
        name, kind, count, indices = (item[key] for key in ("name", "type", "count", "indices"))
        if not isinstance(name, str) or _IDENTIFIER.fullmatch(name) is None or (
            kind is not None and (not isinstance(kind, str) or _IDENTIFIER.fullmatch(kind) is None)
        ):
            raise ValueError("GRES identifier is invalid")
        if (name, kind) in seen or type(count) is not int or not 0 <= count <= _MAX_COUNT:
            raise ValueError("GRES count or identity is invalid")
        if indices is not None and (
            not isinstance(indices, list) or not indices or len(indices) > 4096 or count != len(indices)
            or any(type(index) is not int or not 0 <= index <= _MAX_INDEX for index in indices)
            or indices != sorted(set(indices))
        ):
            raise ValueError("GRES indices are invalid")
        seen.add((name, kind))
        result.append({"name": name, "type": kind, "count": count,
                       "indices": list(indices) if indices is not None else None})
    return result


def _number(value: str) -> int:
    if _NUMBER.fullmatch(value) is None or int(value) > _MAX_COUNT:
        raise ValueError("GRES quantity is invalid")
    return int(value)


def _indices(value: str, *, budget: int) -> list[int]:
    ranges, count = [], 0
    for piece in value.split(",") if value else []:
        match = _INDEX_RANGE.fullmatch(piece)
        if match is None:
            raise ValueError("GRES index range is invalid")
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) is not None else first
        count += last - first + 1
        if first > last or last > _MAX_INDEX or count > 4096:
            raise ValueError("GRES index range exceeds bounds")
        if count > budget:
            raise GresBudgetExceeded("GRES observation index budget exceeded")
        ranges.append((first, last))
    return [index for first, last in ranges for index in range(first, last + 1)]


def parse_native_gres(
    value: object, *, entry_budget: int = MAX_OBSERVATION_GRES_ENTRIES,
    index_budget: int = MAX_OBSERVATION_GRES_INDICES,
) -> list[dict[str, Any]] | None:
    """Read 25.05 gres_stepmgr_job_build_details formats; unknown stays null.

    Shared mps/shard entries carry allocation/capacity pairs internally. Only
    the job's aggregate allocation count may leave this boundary.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= 65536:
        return None
    result, offset, index_count = [], 0, 0
    try:
        while offset < len(value):
            match = _SEGMENT.match(value, offset)
            if match is None or len(result) == 32:
                return None
            if len(result) >= entry_budget:
                raise GresBudgetExceeded("GRES observation entry budget exceeded")
            header, detail = match.groups()
            parts = header.split(":")
            name, indices = parts[0], None
            if detail.startswith("CNT:"):
                if len(parts) not in {1, 2}:
                    return None
                kind = parts[1] if len(parts) == 2 else None
                count = _number(detail[4:])
            else:
                if len(parts) not in {2, 3}:
                    return None
                kind = parts[1] if len(parts) == 3 else None
                count = _number(parts[-1])
                if detail.startswith("IDX:"):
                    indices = _indices(detail[4:], budget=index_budget - index_count)
                    index_count += len(indices)
                elif name in {"mps", "shard"}:
                    pairs = detail.split(",")
                    if not 1 <= len(pairs) <= 4096:
                        return None
                    allocated = 0
                    for pair in pairs:
                        quantities = pair.split("/")
                        if len(quantities) != 2:
                            return None
                        allocated += _number(quantities[0])
                        _number(quantities[1])
                    if allocated != count:
                        return None
                else:
                    return None
            result.append({"name": name, "type": kind, "count": count, "indices": indices})
            offset = match.end()
            if offset < len(value):
                if value[offset] != "," or offset + 1 == len(value):
                    return None
                offset += 1
        return normalize_gres_observation(result)
    except GresBudgetExceeded:
        raise
    except ValueError:
        return None


def job_gres_by_node(item: dict[str, Any], names: list[str]) -> dict[str, list[dict[str, Any]] | None]:
    """Bind per-node GRES indices before presentation reorders node names."""
    resources = item.get("job_resources")
    resource_nodes = resources.get("nodes") if isinstance(resources, dict) else None
    details = item.get("gres_detail")
    if not isinstance(resource_nodes, dict) or not isinstance(details, list):
        return {}
    count, rows = resource_nodes.get("count"), resource_nodes.get("allocation")
    if (
        type(count) is not int or not 1 <= count <= 4096
        or count != len(names) or len(details) != count
        or not isinstance(rows, list) or len(rows) != count
        or resource_nodes.get("list") != item.get("nodes")
    ):
        return {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return {}
        index = row.get("index")
        if type(index) is not int or not 0 <= index < count or index in seen or row.get("name") != names[index]:
            return {}
        seen.add(index)
    result, entries, indices = {}, 0, 0
    try:
        for index, name in enumerate(names):
            observed = parse_native_gres(details[index],
                entry_budget=MAX_OBSERVATION_GRES_ENTRIES - entries,
                index_budget=MAX_OBSERVATION_GRES_INDICES - indices)
            if observed is not None:
                entries += len(observed)
                indices += sum(len(row["indices"] or ()) for row in observed)
            result[name] = observed
    except GresBudgetExceeded:
        return {}
    return result


_MAX_SIGNED_64 = 2**63 - 1

def normalize_job_allocation(item: dict[str, Any]) -> dict[str, Any]:
    """Read v0.0.43 allocation evidence, never requests or step usage.

    The caller must check these rows against Slurm's expansion of ``node_list``
    before publishing them. This is a snapshot, not an asset/attempt identity.
    """
    states = item.get("job_state")
    if (
        not isinstance(states, list)
        or not 1 <= len(states) <= 32
        or any(
            not isinstance(state, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", state) is None
            for state in states
        )
    ):
        raise ValueError("job allocation states are invalid")
    aliases = {"RUNNING": "R", "PENDING": "PD", "COMPLETING": "CG", "SUSPENDED": "S", "COMPLETED": "CD", "FAILED": "F", "CANCELLED": "CA"}
    for key in ("state", "State", "JobState", "ST"):
        if item.get(key) is not None:
            other = item[key]
            other = other[0] if isinstance(other, list) and other else other
            if not isinstance(other, str) or aliases.get(other.strip().upper().split(",")[0], other.strip().upper()) != aliases.get(states[0], states[0]):
                raise ValueError("job allocation states are inconsistent")
            break
    restart_count = item.get("restart_cnt")
    if restart_count is not None and (
        type(restart_count) is not int or not 0 <= restart_count <= 65535
    ):
        raise ValueError("job restart count is invalid")
    result = {
        "scheduler_states": states,
        "restart_count": restart_count,
        "status": "unavailable",
        "nodes": None,
        "node_list": None,
    }
    # Flags such as COMPLETING/RESIZING can retain resources after a base state
    # changes. An aggregate array cannot prove a particular task's allocation.
    if len(states) != 1:
        return result
    state = states[0]
    if state in {
        "PENDING", "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE",
        "FAILED", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "TIMEOUT",
    }:
        return {**result, "status": "not_allocated", "nodes": []}
    if (
        state not in {"RUNNING", "SUSPENDED", "STOPPED", "CONFIGURING"}
        or item.get("array_task_string")
    ):
        return result
    resources = item.get("job_resources")
    if resources is None:
        return result
    if not isinstance(resources, dict):
        raise ValueError("job resources are invalid")
    resource_nodes = resources.get("nodes")
    if resource_nodes is None:
        return result
    if not isinstance(resource_nodes, dict):
        raise ValueError("job resource nodes are invalid")
    allocation = resource_nodes.get("allocation")
    if allocation is None or allocation == []:
        return result
    if not isinstance(allocation, list) or len(allocation) > 4096:
        raise ValueError("job node allocation is invalid")
    node_list = item.get("nodes")
    if node_list is None or node_list == "":
        return result
    if not isinstance(node_list, str) or len(node_list) > 4096:
        raise ValueError("job node list is invalid")
    nodes: list[dict[str, Any]] = []
    names: set[str] = set()
    for row in allocation:
        if not isinstance(row, dict):
            raise ValueError("job node allocation row is invalid")
        name, cpus, memory = row.get("name"), row.get("cpus"), row.get("memory")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is None
            or name in names
        ):
            raise ValueError("job allocation node identity is invalid")
        count = cpus.get("count") if isinstance(cpus, dict) else None
        if type(count) is not int or not 0 <= count <= _MAX_SIGNED_64:
            raise ValueError("job allocated CPU count is invalid")
        if memory is not None and not isinstance(memory, dict):
            raise ValueError("job allocated memory is invalid")
        memory_mib = memory.get("allocated") if memory is not None else None
        if memory_mib is not None and (
            type(memory_mib) is not int or not 0 <= memory_mib <= _MAX_SIGNED_64
        ):
            raise ValueError("job allocated memory is invalid")
        names.add(name)
        nodes.append({"name": name, "cpus": count, "memory_mib": memory_mib, "gres": None})
    return {**result, "status": "allocated", "nodes": nodes, "node_list": node_list}


MAX_OBSERVATION_CPU_IDS = 262144


def normalize_cpu_ids(value: object) -> list[int] | None:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) > 65536
            or any(type(index) is not int or not 0 <= index < 65536 for index in value)
            or value != sorted(set(value))):
        raise ValueError("invalid Slurm CPU IDs")
    return list(value)


def normalize_cpu_topology(value: object) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid CPU topology")
    result = {key: value.get(key) for key in ("sockets", "cores_per_socket", "threads_per_core")}
    if any(type(number) is not int or not 1 <= number <= 65536 for number in result.values()):
        raise ValueError("invalid CPU dimensions")
    if result["sockets"] * result["cores_per_socket"] * result["threads_per_core"] > 65536:
        raise ValueError("CPU dimensions exceed bounds")
    return result


def normalize_node_topology(row: dict) -> dict:
    """Allowlist the additive allocation fields for every Python consumer."""
    if "cpu_ids" not in row:
        return {}
    ids = normalize_cpu_ids(row["cpu_ids"])
    dimensions = normalize_cpu_topology(row.get("cpu_topology"))
    total = row.get("gpu_total")
    if total is not None and (type(total) is not int or not 0 <= total <= 4096):
        raise ValueError("invalid GPU capacity")
    if ids is not None and dimensions is None:
        raise ValueError("CPU IDs require native dimensions")
    if dimensions is not None and ids and ids[-1] >= dimensions["sockets"] * dimensions["cores_per_socket"] * dimensions["threads_per_core"]:
        raise ValueError("CPU IDs outside native dimensions")
    return {"cpu_ids": ids, "cpu_topology": dimensions, "gpu_total": total}


def node_dimensions(row: dict) -> dict[str, int] | None:
    result = {}
    for key, source in (("sockets", "sockets"), ("cores_per_socket", "cores"), ("threads_per_core", "threads")):
        pair = row.get(source)
        if pair is None:
            return None
        if not isinstance(pair, dict) or pair.get("minimum") != pair.get("maximum"):
            raise ValueError("node dimensions are not per-node")
        number = pair.get("minimum")
        if number in {None, 0, 65534, 65535}:
            return None
        result[key] = number
    return normalize_cpu_topology(result)


def node_topology_command(names: list[str], binary: str = "sinfo") -> list[str]:
    if (not 1 <= len(names) <= 4096 or len(set(names)) != len(names)
            or any(not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is None for name in names)):
        raise ValueError("invalid allocated node selectors")
    return [binary, "--json", "--local", "--Node", "--nodes=" + ",".join(names)]


def _node_topologies(payload: object, names: list[str]) -> dict[str, dict]:
    if not isinstance(payload, dict) or payload.get("errors") != [] or not isinstance(payload.get("sinfo"), list):
        raise ValueError("invalid node topology response")
    result = {}
    expected = set(names)
    for row in payload["sinfo"]:
        if not isinstance(row, dict) or not isinstance(row.get("nodes"), dict):
            raise ValueError("invalid node topology")
        members = row["nodes"].get("nodes")
        if not isinstance(members, list) or len(members) != 1 or members[0] not in expected:
            raise ValueError("topology nodes differ from allocation")
        gres = row.get("gres")
        counts = gpu_counts(gres.get("total") if isinstance(gres, dict) else None)
        total = None if counts is None else counts[None] if None in counts else sum(counts.values())
        clean = {"cpu": node_dimensions(row), "gpu_total": total if total is None or total <= 4096 else None}
        name = members[0]
        if name in result and result[name] != clean:
            raise ValueError("conflicting node dimensions")
        result[name] = clean
    if set(result) != expected:
        raise ValueError("missing allocated node dimensions")
    return result


def _allocated_cpu_ids(row: dict, dimensions: dict | None) -> tuple[list[int] | None, dict | None]:
    sockets = row.get("sockets")
    if sockets is None or dimensions is None:
        return None, None
    if not isinstance(sockets, list) or not 1 <= len(sockets) <= 1024:
        return None, None
    if len(sockets) != dimensions["sockets"]:
        return None, None
    cpu_ids, core_count = [], None
    threads = dimensions["threads_per_core"]
    for socket_index, socket in enumerate(sockets):
        if not isinstance(socket, dict) or type(socket.get("index")) is not int or socket["index"] != socket_index:
            return None, None
        cores = socket.get("cores")
        if not isinstance(cores, list) or not 1 <= len(cores) <= 65536:
            return None, None
        if core_count is not None and core_count != len(cores):
            return None, None
        core_count = len(cores)
        if core_count != dimensions["cores_per_socket"]:
            return None, None
        if len(sockets) * core_count * threads > 65536:
            return None, None
        for core_index, core in enumerate(cores):
            if not isinstance(core, dict) or type(core.get("index")) is not int or core["index"] != core_index:
                return None, None
            flags = core.get("status")
            if flags not in (["ALLOCATED"], ["ALLOCATED", "IN_USE"], ["UNALLOCATED"]):
                return None, None
            if "ALLOCATED" in flags:
                # Same Slurm numbering as scontrol/info_job.c: stored core
                # bitmap times the NODE thread count, not requested threads.
                start = (socket_index * core_count + core_index) * threads
                cpu_ids.extend(range(start, start + threads))
    return cpu_ids, {"sockets": len(sockets), "cores_per_socket": core_count, "threads_per_core": threads}


def bind_job_topology(item: dict, allocation: dict, names: list[str], node_payload: dict) -> dict:
    node_topology_command(names)
    if set(names) != {row["name"] for row in allocation["nodes"]}:
        return {**allocation, "status": "unavailable", "nodes": None}
    dimensions = _node_topologies(node_payload, names)
    gres = job_gres_by_node(item, names)
    raw_nodes = {row["name"]: row for row in item["job_resources"]["nodes"]["allocation"]}
    nodes, count = [], 0
    for row in allocation["nodes"]:
        native = dimensions[row["name"]]
        cpu_ids, cpu_topology = _allocated_cpu_ids(raw_nodes[row["name"]], native["cpu"])
        count += len(cpu_ids or ())
        if count > MAX_OBSERVATION_CPU_IDS:
            raise ValueError("job CPU topology exceeds bounds")
        nodes.append({**row, "gres": gres.get(row["name"]), "cpu_ids": cpu_ids,
                      "cpu_topology": cpu_topology, "gpu_total": native["gpu_total"]})
    return {**allocation, "nodes": sorted(nodes, key=lambda row: row["name"])}


_GRES = re.compile(r"([^(),]+)(?:\(([^()]*)\))?(?:,|$)")

def gpu_counts(value: object) -> dict[str | None, int] | None:
    """Read configured/allocated GRES counts independently of index metadata."""
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 65536:
        return None
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
            result[kind] = _number(parts[-1])
        offset = match.end()
    return result


def gpu_indices(value: object, total: int | None, allocated: int | None) -> list[int] | None:
    """Keep native IDX positions only when the complete set agrees with the count."""
    if total is None or allocated is None or not 0 <= allocated <= total <= 4096:
        return None
    if allocated == 0:
        return []
    if not isinstance(value, str):
        return None
    entries: dict[str | None, set[int] | None] = {}
    for match in _GRES.finditer(value):
        parts = match[1].split(":")
        if parts[0] != "gpu":
            continue
        kind = parts[1] if len(parts) == 3 else None
        metadata = match[2] or ""
        indices: set[int] = set()
        if metadata.startswith("IDX:"):
            for piece in metadata[4:].split(","):
                span = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", piece)
                if span is None:
                    break
                first, last = int(span[1]), int(span[2] or span[1])
                if not 0 <= first <= last < total or indices.intersection(range(first, last + 1)):
                    break
                indices.update(range(first, last + 1))
            else:
                if len(indices) == int(parts[-1]):
                    entries[kind] = indices
                    continue
        entries[kind] = set() if parts[-1] == "0" else None
    if None in entries:
        indices = entries[None]
        if indices is None or any(item is not None and not item <= indices for item in entries.values()):
            return None
    else:
        indices = set()
        for item in entries.values():
            if item is None or indices.intersection(item):
                return None
            indices.update(item)
    return sorted(indices) if len(indices) == allocated else None



def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get("set") is False:
            return None
        for key in ("number", "value", "name", "id", "string", "text"):
            if value.get(key) is not None:
                return as_text(value.get(key))
        return None
    if isinstance(value, list):
        clean = []
        for item in value:
            text = as_text(item)
            if text:
                clean.append(text)
        return ",".join(clean) if clean else None
    text = str(value).strip()
    return text or None


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item.get(key) is not None:
            return item.get(key)
    return None


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    return as_text(_first_value(item, *keys))

def normalize_job_id(value: Any) -> str | None:
    text = as_text(value)
    if not text:
        return None
    job_id = text.split(".", 1)[0].strip()
    return job_id if job_id and job_id != "0" else None


def _job_identity(value: Any) -> str | None:
    text = as_text(value)
    if not text:
        return None
    if "_" in text:
        base, task = text.split("_", 1)
        return f"{base.strip()}_{task.strip()}" if base.strip() and task.strip() else None
    if "." in text:
        base, suffix = text.split(".", 1)
        if suffix.strip().isdigit() and base.strip():
            return f"{base.strip()}_{suffix.strip()}"
    return normalize_job_id(text)


def _base_array_job_id(identity: str | None) -> tuple[str | None, str | None]:
    if not identity or "_" not in identity:
        return identity, None
    base, task = identity.split("_", 1)
    return (base.strip() or None), (task.strip() or None)


def _explicit_array_task_id(item: dict[str, Any]) -> str | None:
    task = _first_text(
        item,
        "array_task_id",
        "array_id",
        "ArrayTaskId",
        "ArrayTaskID",
        "array_ID",
        "array_task",
    )
    if task and task != "4294967294":
        return task
    return None


def visibility_item_job_id(item: dict[str, Any]) -> str | None:
    raw = _job_identity(_first_value(item, "JobIDRaw", "job_id_raw", "jobidraw", "JobID", "job_id", "jobid", "id"))
    if raw and "_" in raw:
        return raw
    task = _explicit_array_task_id(item)
    if task:
        base = normalize_job_id(_first_value(item, "array_job_id", "ArrayJobId", "ArrayJobID")) or raw
        if base:
            return f"{base}_{task}"
    return raw


def select_job_visibility_item(item: dict[str, Any], job_id: str) -> dict[str, Any] | None:
    """Select one native record, including a task in an unsplit array."""
    if visibility_item_job_id(item) == job_id:
        return item
    parent, separator, task = job_id.partition("_")
    if not separator or not task.isdecimal():
        return None
    if normalize_job_id(_first_value(item, "array_job_id", "ArrayJobId", "ArrayJobID")) != parent:
        return None
    tasks = _first_text(item, "array_task_string") or ""
    for group in tasks.split("%", 1)[0].split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+)(?::(\d+))?)?", group)
        if match is None:
            continue
        first, last = int(match[1]), int(match[2] or match[1])
        step = int(match[3] or 1)
        if step > 0 and int(task) in range(first, last + 1, step):
            return dict(item, JobIDRaw=job_id, array_task_id=int(task))
    return None
