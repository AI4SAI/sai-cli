"""Local exact-job observation using the site's shared native projection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import os
import re
from typing import Mapping

from sai_native_slurm import normalize_job_allocation, bind_job_topology, node_topology_command, select_job_visibility_item
from .errors import ConfigError, NotFoundError
from .local_jobs import _item
from .native_process import read_native_json, read_native_output
from .native_values import local_options, native_environment, native_header, native_user, invalid_native


@dataclass(frozen=True)
class NativeTopology:
    values: dict

    def as_dict(self) -> dict:
        return self.values


def read_local_job_topology(args: argparse.Namespace, *, environ: Mapping[str, str]) -> NativeTopology:
    timeout = local_options(args, command="jobs local")
    job_id = args.job_id
    if not isinstance(job_id, str) or re.fullmatch(r"[0-9]{1,20}(?:_[0-9]{1,20})?", job_id) is None:
        raise ConfigError("--job-id requires one numeric job ID or array task ID")
    if any(getattr(args, key, None) not in (None, False) for key in
           ("accounts", "users", "partition", "qos", "states", "with_subaccounts", "limit")):
        raise ConfigError("--job-id cannot be combined with queue filters")
    env = native_environment(environ, filter_prefix="SQUEUE_")
    env = {key: value for key, value in env.items() if not key.startswith("SINFO_")}
    payload = read_native_json(["scontrol", "--local", "show", "job", job_id, "--json"], environ=env, timeout=timeout)
    cluster, warnings = native_header(payload)
    observed = datetime.now(timezone.utc).replace(microsecond=0)
    if not isinstance(payload.get("jobs"), list):
        raise invalid_native()
    if any(not isinstance(raw, dict) for raw in payload["jobs"]):
        raise invalid_native()
    selected = [chosen for raw in payload["jobs"] if (chosen := select_job_visibility_item(raw, job_id)) is not None]
    jobs = [(raw, _item(raw, observed=int(observed.timestamp()))) for raw in selected]
    jobs = [(raw, job) for raw, job in jobs if job.canonical_id == job_id]
    if not jobs:
        raise NotFoundError("The job is absent from the native queue.")
    if len(jobs) != 1:
        raise invalid_native()
    raw, job = jobs[0]
    try:
        allocation = normalize_job_allocation(raw)
        if allocation["status"] == "allocated":
            names = read_native_output(["scontrol", "show", "hostnames", allocation["node_list"]], environ=env,
                timeout=timeout, max_output_bytes=1024 * 1024, reject_stderr=True).decode("utf-8").splitlines()
            command = node_topology_command(names)
            if set(names) != {row["name"] for row in allocation["nodes"]}:
                allocation = {**allocation, "status": "unavailable", "nodes": None}
            else:
                nodes = read_native_json(command, environ=env, timeout=timeout)
                node_cluster, node_warnings = native_header(nodes)
                warnings += node_warnings
                if node_cluster != cluster:
                    raise ValueError("native cluster changed")
                allocation = bind_job_topology(raw, allocation, names, nodes)
    except (ValueError, UnicodeError) as exc:
        raise invalid_native() from exc
    result = {"schema_version": "native.job-allocation/v1", "source": "scontrol", "authority": "native",
        "cluster": cluster, "actor": {"user": native_user(), "uid": os.geteuid()}, "job": job.as_dict(),
        "observed_at": observed.isoformat().replace("+00:00", "Z"), "warning_count": warnings,
        "scheduler_states": allocation["scheduler_states"], "restart_count": allocation["restart_count"],
        "allocation": {key: allocation[key] for key in ("status", "nodes")}}
    if getattr(args, "with_interconnect", False):
        from sai_native_topology import join_interconnect
        try:
            result["interconnect"] = join_interconnect(allocation, cluster=cluster,
                read_node_state=lambda names: read_native_json(
                    ["scontrol", "--local", "show", "node", ",".join(names), "--json"], environ=env, timeout=timeout))
        except (ValueError, KeyError, TypeError) as exc:
            raise invalid_native() from exc
    return NativeTopology(result)
