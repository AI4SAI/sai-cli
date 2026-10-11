# Local job allocation

`sai jobs local --job-id 12345` returns `native.job-allocation/v1` under the
current Unix identity. It bypasses Portal configuration, OAuth and the gateway.
Queue filters cannot accompany the exact selector; array task zero is preserved.

The envelope contains `source=scontrol`, `authority=native`, `cluster`, `actor`,
`job`, `observed_at`, `warning_count`, `scheduler_states`, `restart_count` and
`allocation`. The job summary uses the existing native jobs fields. Allocation
uses the same node projection as gateway `jobs.allocation/v2` and `/v3`:
`name`, `cpus`, `memory_mib`, `gres`, `cpu_ids`, `cpu_topology` and `gpu_total`.
Pending and completed observations retain `not_allocated`; missing or
transitional evidence remains `unavailable`. No file paths, environment or
native diagnostic text leave the reader.

An allocated observation performs three bounded native reads: one exact
`scontrol --local show job ID --json`, the existing native hostlist expansion,
and one `sinfo --json --local --Node --nodes=...` restricted to those verified
nodes. An unallocated job needs only its job observation. There is no per-node
SSH, historical query, collector or privilege change.

CPU IDs follow Slurm's `scontrol` numbering: the job's stored socket/core bitmap
is expanded using each node's configured threads per core. The job's requested
`threads_per_core`, allocated CPU count and OS/Linux processor IDs are not
substitutes. CPU ID count can therefore differ from billed/allocated CPU slots.
`cpu_topology` describes Slurm's socket/core/thread dimensions; it is not a
claim about NUMA locality, process affinity, utilization or physical wiring.
GPU indices retain the original GRES IDX units and typed resources. Unknown
dimensions/indices remain null, independently of valid allocations.

The canonical standard-library module is `sai_native_slurm.py` in the Portal
source. `scripts/sync_native_slurm.py --source /path/to/producer` exports that
file byte for byte into this package, with its commit and SHA-256 recorded in
`contracts/native-slurm-source.json`. CI checks the digest; paired verification
also checks against the producer. Do not edit the exported parser independently.
Web/Pilot reads this DTO through the existing authorized read path and only
renders it. The standalone CLI still needs no additional runtime dependency.

Source implementation is distinct from shared CLI, gateway and Web deployment.
