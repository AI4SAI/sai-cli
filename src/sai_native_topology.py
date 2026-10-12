"""Shared, dependency-free hardware interconnect facts. No SSH or UI code.

The operator records native hardware observations once. Readers join only the
allocated nodes; live job allocation remains owned by Slurm.
"""
from __future__ import annotations

from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET

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


def _range(value):
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError("invalid native range")
    numbers = []
    for part in value.split(","):
        if re.fullmatch(r"[0-9]{1,5}(?:-[0-9]{1,5})?", part) is None:
            raise ValueError("invalid native range")
        ends = list(map(int, part.split("-")))
        if ends[0] > ends[-1] or ends[-1] > 65535:
            raise ValueError("invalid native range")
        numbers.extend(range(ends[0], ends[-1] + 1))
        if len(numbers) > 65536:
            raise ValueError("native range exceeds bound")
    return _ids(numbers)


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


def parse_nvidia_topology(text):
    """NVIDIA path classes are relationships, not inferred PCIe wiring."""
    if not isinstance(text, str) or len(text) > MAX_BYTES:
        raise ValueError("invalid NVIDIA topology text")
    # NVIDIA emits an underlined header even with piped stdout on some drivers.
    text = re.sub(r"\x1b\[(?:0|4)m", "", text)
    if any(ord(char) < 32 and char not in "\r\n\t" or 127 <= ord(char) <= 159 for char in text):
        raise ValueError("invalid NVIDIA topology text")
    lines = [line.split() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("missing NVIDIA topology")
    header = []
    for name in lines[0]:
        if re.fullmatch(r"(?:GPU|NIC)[0-9]{1,2}", name):
            header.append(name)
        else:
            break
    if not header or len(header) > 128 or len(set(header)) != len(header):
        raise ValueError("invalid NVIDIA topology header")
    rows = {}
    for words in lines[1:]:
        if words[0] not in header:
            continue
        name = words[0]
        if name in rows or len(words) < len(header) + 1:
            raise ValueError("duplicate or incomplete GPU matrix")
        paths = words[1:len(header) + 1]
        for other, kind in zip(header, paths):
            if (kind != "X" if name == other else _PATH.fullmatch(kind) is None):
                raise ValueError("invalid NVIDIA path class")
        affinity = words[len(header) + 1:]
        numa = None
        cpus = None
        if name.startswith("GPU"):
            if len(affinity) < 2:
                raise ValueError("missing GPU affinity columns")
            cpus = None if affinity[0] == "N/A" else _range(affinity[0])
            numa = None if affinity[1] == "N/A" else _number(int(affinity[1]))
        rows[name] = {"paths": dict(zip(header, paths)), "linux_cpus": cpus, "numa": numa}
    if set(rows) != set(header):
        raise ValueError("incomplete NVIDIA matrix")
    for a in header:
        for b in header:
            if rows[a]["paths"][b] != rows[b]["paths"][a]:
                raise ValueError("asymmetric NVIDIA paths")
    return rows


def _gpu_files(value):
    """The NVIDIA subset of Slurm File hostlists, preserving expansion order."""
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("invalid GRES files")
    offset, result = 0, []
    pattern = re.compile(r"/dev/nvidia(?:([0-9]{1,5})|\[([0-9,-]+)\])(?:,|$)")
    while offset < len(value):
        match = pattern.match(value, offset)
        if match is None:
            raise ValueError("unsupported GRES file")
        for item in (match[1] or match[2]).split(','):
            if re.fullmatch(r'[0-9]{1,5}(?:-[0-9]{1,5})?', item) is None:
                raise ValueError("invalid GRES file range")
            ends = [int(part) for part in item.split('-')]
            if ends[0] > ends[-1] or ends[-1] > 65535 or len(result) + ends[-1] - ends[0] + 1 > 64:
                raise ValueError("GRES files exceed bound")
            result.extend(range(ends[0], ends[-1] + 1))
        offset = match.end()
    if not result or len(set(result)) != len(result):
        raise ValueError("duplicate or empty GRES files")
    return result


def parse_gres_diagnostic(text, *, threads):
    """Operator-only slurmd -G capture. Never execute slurmd in a reader."""
    if not isinstance(text, str) or len(text) > 4 * MAX_BYTES or type(threads) is not int or not 1 <= threads <= MAX_CPU_IDS:
        raise ValueError("invalid GRES diagnostic")
    result, minors_seen = {}, set()
    for line in text.splitlines():
        if "Gres Name=gpu " not in line:
            continue
        fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
        # Slurm's diagnostic Index is a filename suffix, not a bitmap index.
        # gres_node_config_load assigns indices in final File expansion order.
        minors = _gpu_files(fields["File"])
        if (int(fields["Count"]) != len(minors) or len(result) + len(minors) > 64 or
                'HAS_MULT' in fields.get('Flags', '').split(',') or minors_seen.intersection(minors)):
            raise ValueError("unsupported GRES device mapping")
        cores = fields.get("Cores")
        core_ids = None if cores in {None, "(null)"} else _range(cores)
        if core_ids and (len(core_ids) * threads > MAX_CPU_IDS or (core_ids[-1] + 1) * threads > MAX_CPU_IDS):
            raise ValueError("GRES CPU mapping exceeds bound")
        cpus = None if core_ids is None else [core * threads + thread for core in core_ids for thread in range(threads)]
        for minor in minors:
            result[len(result)] = {"minor": minor, "cpu_ids": cpus}
        minors_seen.update(minors)
    if not result or set(result) != set(range(len(result))):
        raise ValueError("incomplete GRES mapping")
    return result


def _cpu_domains(cpu_json):
    cpus = cpu_json.get("cpus")
    if not isinstance(cpus, list) or not cpus or len(cpus) > 65536:
        raise ValueError("missing Linux CPU topology")
    domains = {}
    for row in cpus:
        domain, package, cpu = (int(row[key]) for key in ("node", "socket", "cpu"))
        entry = domains.setdefault(domain, {"id": domain, "packages": set(), "linux_cpu_ids": []})
        entry["packages"].add(package)
        entry["linux_cpu_ids"].append(cpu)
    domains = [{**row, "packages": sorted(row["packages"]), "linux_cpu_ids": sorted(row["linux_cpu_ids"])}
               for _, row in sorted(domains.items())]
    return domains


def parse_slurm_cpu_mapping(text, *, dimensions, linux_cpu_ids):
    """Read Slurm's native abstract-to-machine map, never infer Linux ordering."""
    if not isinstance(text, str) or len(text) > 4 * MAX_BYTES:
        raise ValueError("invalid CPU mapping capture")
    headers = re.findall(r"^NodeName=[^\s]+ CPUs=([0-9]+) Boards=[0-9]+ SocketsPerBoard=[0-9]+ CoresPerSocket=[0-9]+ ThreadsPerCore=([0-9]+)\b", text, re.M)
    if len(headers) != 1:
        raise ValueError("missing native CPU dimensions")
    native_total, native_threads = (_number(int(item), MAX_CPU_IDS) for item in headers[0])
    threads = _number(dimensions["threads_per_core"])
    total = _number(dimensions["sockets"]) * _number(dimensions["cores_per_socket"]) * threads
    if not 1 <= total <= MAX_CPU_IDS or not 1 <= threads <= native_threads or not 1 <= native_total <= MAX_CPU_IDS:
        raise ValueError("CPU dimensions cannot be mapped")
    rows = [line for line in text.splitlines() if "CPU map[" in line]
    if len(rows) != native_total:
        raise ValueError("incomplete native CPU map")
    mapping = {}
    for line in rows:
        match = re.search(r"CPU map\[([0-9]+)\]=>([0-9]+) S:C:T [0-9]+:[0-9]+:([0-9]+)$", line.strip())
        if match is None:
            raise ValueError("invalid native CPU map row")
        abstract, machine, thread = (_number(int(item)) for item in match.groups())
        if abstract in mapping or thread != abstract % native_threads:
            raise ValueError("inconsistent native CPU map")
        mapping[abstract] = machine
    if set(mapping) != set(range(native_total)) or len(set(mapping.values())) != native_total or set(mapping.values()) != set(_ids(linux_cpu_ids)):
        raise ValueError("native CPU map differs from Linux topology")
    # scontrol expands the core bitmap by configured threads; Slurm's native
    # binding indexes the block map with the actual hardware thread stride.
    indices = [cpu // threads * native_threads + cpu % threads for cpu in range(total)]
    if indices[-1] >= native_total:
        raise ValueError("configured CPUs exceed native CPU map")
    return [mapping[index] for index in indices]


def job_cpu_locality(record, cpu_ids):
    """Project allocation onto NUMA using only the recorded native CPU map."""
    mapping = record.get("cpu_mapping")
    if mapping is None or cpu_ids is None:
        return None
    cpus = _ids(cpu_ids, len(mapping["slurm_to_linux"]) - 1)
    machine = {mapping["slurm_to_linux"][cpu] for cpu in cpus}
    return {row["id"]: sorted(machine.intersection(row["linux_cpu_ids"])) for row in record["numa"]}


def build_interconnect(*, node, cluster, observed_at, expires_at, dimensions, gpu_total, gpu_csv, gpu_xml, gpu_matrix,
                       gres_diagnostic, cpu_json, boot_time, slurmd_start_time, nic_peers=None, pcie=None, fabric_text=None):
    """Join verified native identities before discarding minor numbers/paths."""
    if not isinstance(dimensions, dict):
        raise ValueError("invalid scheduler dimensions")
    dimensions = {key: _number(dimensions.get(key)) for key in
                  ("sockets", "cores_per_socket", "threads_per_core")}
    total = dimensions["sockets"] * dimensions["cores_per_socket"] * dimensions["threads_per_core"]
    if not 1 <= total <= MAX_CPU_IDS:
        raise ValueError("scheduler dimensions exceed bound")
    _number(gpu_total, 64)
    base = {"schema_version": SCHEMA, "node": node, "cluster": cluster,
            "observed_at": observed_at, "expires_at": expires_at, "cpu_topology": dimensions,
            "boot_time": boot_time, "slurmd_start_time": slurmd_start_time,
            "fabric_links": [] if fabric_text is None else parse_fabric_links(fabric_text),
            "numa": _cpu_domains(cpu_json)}
    if gpu_total == 0:
        if any((gpu_csv, gpu_xml, gpu_matrix, gres_diagnostic)):
            raise ValueError("GPU evidence contradicts a CPU-only node")
        nics = [{"index": index, "gpu_paths": [], **peer} for index, peer in sorted((nic_peers or {}).items())]
        return normalize_interconnect({**base, "gpus": [], "links": [], "nics": nics})
    matrix = parse_nvidia_topology(gpu_matrix)
    gres = parse_gres_diagnostic(gres_diagnostic, threads=dimensions["threads_per_core"])
    if not isinstance(gpu_csv, str) or len(gpu_csv) > MAX_BYTES:
        raise ValueError("invalid GPU identity capture")
    if not isinstance(gpu_xml, str) or len(gpu_xml) > 4 * MAX_BYTES:
        raise ValueError("invalid NVIDIA XML")
    devices = ET.fromstring(gpu_xml).findall("gpu")
    if len(devices) > 64:
        raise ValueError("GPU device limit exceeded")
    minors = {device.attrib["id"].lower(): int(device.findtext("minor_number")) for device in devices}
    gpu_indices, bus_ids = {}, {}
    for row in csv.reader(io.StringIO(gpu_csv)):
        if len(row) != 2:
            raise ValueError("expected NVIDIA index and PCI bus ID")
        index, minor = int(row[0].strip()), minors[row[1].strip().lower()]
        if index in gpu_indices or minor in gpu_indices.values():
            raise ValueError("duplicate NVIDIA device identity")
        gpu_indices[index] = minor
        bus_ids[index] = row[1].strip().lower()
    if len(gres) != gpu_total or set(gpu_indices.values()) != {row["minor"] for row in gres.values()}:
        raise ValueError("Slurm and NVIDIA devices differ")
    native_to_slurm = {"GPU" + str(native): index for native, minor in gpu_indices.items()
                       for index, row in gres.items() if row["minor"] == minor}
    if set(native_to_slurm) != {name for name in matrix if name.startswith("GPU")}:
        raise ValueError("NVIDIA matrix identity differs")
    domains = base["numa"]
    links, gpus, nics = [], [], []
    for native, index in native_to_slurm.items():
        row = matrix[native]
        domain = next((item for item in domains if item["id"] == row["numa"]), None)
        if row["numa"] is not None and (domain is None or row["linux_cpus"] != domain["linux_cpu_ids"]):
            raise ValueError("NVIDIA and Linux NUMA affinity differ")
        gpus.append({"index": index, "numa": row["numa"], "cpu_ids": gres[index]["cpu_ids"], "pcie_path": None})
        for other, target in native_to_slurm.items():
            if index < target:
                links.append({"a": index, "b": target, "kind": row["paths"][other]})
    if pcie is not None:
        paths = parse_pcie_paths(pcie, {native_to_slurm['GPU' + str(index)]: address for index, address in bus_ids.items()})
        for gpu in gpus:
            path, numa = paths[gpu["index"]]
            if numa is not None and numa != gpu["numa"]:
                raise ValueError("PCIe and NVIDIA affinity differ")
            gpu["pcie_path"] = path
    for native in matrix:
        if not native.startswith("NIC"):
            continue
        index = int(native[3:])
        peer = (nic_peers or {}).get(index, {})
        nics.append({"index": index, "peer": peer.get("peer"), "rate_gbps": peer.get("rate_gbps"),
                     "gpu_paths": [{"gpu": index, "kind": matrix[gpu]["paths"][native]}
                                   for gpu, index in native_to_slurm.items()]})
    return normalize_interconnect({**base,
        "gpus": sorted(gpus, key=lambda row: row["index"]), "links": links, "nics": nics})


def parse_pcie_paths(rows, gpu_bus_ids):
    """Project sysfs ancestry while keeping PCI addresses inside the producer."""
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ValueError("invalid PCIe capture")
    devices = {}
    for row in rows:
        address = row["address"]
        if not isinstance(address, str) or re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", address) is None or address in devices:
            raise ValueError("invalid PCI address")
        devices[address] = row
    references, result = {}, {}
    for index, address in sorted(gpu_bus_ids.items()):
        # NVIDIA uses an eight-digit domain; sysfs uses the native four digits.
        address = address[4:] if address.startswith("0000") and len(address) == 16 else address
        row = devices[address]
        path = row["path"]
        if not isinstance(path, str) or len(path) > 4096 or not path.startswith("/sys/devices/"):
            raise ValueError("invalid PCI sysfs ancestry")
        parts = path.removeprefix("/sys/devices/").split("/")
        if not 2 <= len(parts) <= 33 or parts[-1] != address or re.fullmatch(r"pci[0-9a-f]{4}:[0-9a-f]{2}", parts[0]) is None:
            raise ValueError("invalid PCI root")
        if row["class"] >> 16 != 3:
            raise ValueError("GPU PCI class differs")
        safe = []
        for offset, parent in enumerate(parts[:-1]):
            if offset and (parent not in devices or devices[parent]["class"] >> 16 != 6):
                raise ValueError("PCI ancestor is not a bridge")
            if parent not in references:
                references[parent] = ("root-" if offset == 0 else "bridge-") + str(len(references))
            safe.append(references[parent])
        result[index] = safe, None if row["numa"] == -1 else _number(row["numa"])
    return result


def parse_ib_neighbor(text, *, rate, local_guid):
    """One local HCA -> peer observation from iblinkinfo -D 0 -n 0 -l.

    GUIDs identify equality inside the site, but never leave this parser.
    A peer is not evidence of an end-to-end route or available bandwidth.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1 or len(lines[0]) > 4096:
        raise ValueError("expected one direct IB neighbor")
    match = re.fullmatch(r'(?P<local>0x[0-9a-fA-F]{16})\s+"[^"\x00-\x1f]+"\s+\d+\s+\d+\[[^]]*\]\s+==\([^)]*Active/\s*LinkUp\)==>\s+(?P<peer>0x[0-9a-fA-F]{16})\s+\d+\s+\d+\[[^]]*\]\s+"[^"\x00-\x1f]+"\s+\(\s*\)', lines[0])
    speed = re.fullmatch(r"([0-9]+) Gb/sec(?: \([^\n]+\))?\s*", rate)
    if not isinstance(local_guid, str) or re.fullmatch(r"[0-9a-fA-F]{4}(?::[0-9a-fA-F]{4}){3}", local_guid.strip()) is None:
        raise ValueError("invalid local HCA identity")
    if match is None or speed is None or match['local'].lower() != '0x' + local_guid.strip().replace(':','').lower():
        raise ValueError("IB neighbor is not an active observed link")
    return {"peer": "endpoint-" + hashlib.sha256(match['peer'].lower().encode()).hexdigest()[:24],
            "rate_gbps": int(speed[1])}


def bind_nic_peers(matrix, captures):
    """Bind NVIDIA's NIC legend to the captured native HCA and its GUID."""
    if not isinstance(captures, dict) or len(captures) > 64:
        raise ValueError("invalid NIC captures")
    legend = dict((name, int(index)) for index, name in re.findall(r'^\s*NIC([0-9]{1,2}):\s+([A-Za-z0-9_.-]{1,128})\s*$', matrix, re.M))
    if matrix and any(name not in legend for name in captures):
        raise ValueError("NIC capture is absent from NVIDIA legend")
    if not matrix:
        legend = {name:index for index,name in enumerate(sorted(captures))}
    return {legend[name]:parse_ib_neighbor(row['link'], rate=row['rate'], local_guid=row['node_guid'])
            for name,row in captures.items()}


def parse_fabric_links(text):
    """Observed active links from one bounded iblinkinfo line-mode capture."""
    if not isinstance(text, str) or len(text) > MAX_BYTES:
        raise ValueError("fabric capture exceeds bound")
    links = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(line) > 4096 or not re.match(r'^0x[0-9a-fA-F]{16}\s+"', line):
            raise ValueError("invalid fabric line")
        match = re.fullmatch(r'(?P<a>0x[0-9a-fA-F]{16})\s+"[^"\x00-\x1f]+"\s+\d+\s+\d+\[[^]]*\]\s+==\([^)]*Active/\s*LinkUp\)==>\s+(?P<b>0x[0-9a-fA-F]{16})\s+\d+\s+\d+\[[^]]*\]\s+"[^"\x00-\x1f]+"\s+\(\s*\)', line.strip())
        if match is None:
            if re.search(r"==\([^)]*\b(?:Down|Initialize|Armed)/\s*[A-Za-z]+\)", line):
                continue
            raise ValueError("unrecognized fabric link state")
        refs = tuple(sorted("endpoint-" + hashlib.sha256(match[key].lower().encode()).hexdigest()[:24] for key in ("a", "b")))
        if refs[0] == refs[1]:
            raise ValueError("fabric connection loops to itself")
        links.add(refs)
    return [{"a": a, "b": b, "kind": "infiniband"} for a, b in sorted(links)]


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
