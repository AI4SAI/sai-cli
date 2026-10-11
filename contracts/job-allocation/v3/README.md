# Organization job read scope

This schema extends the preceding exact-account DTO for an organization with
authorized project accounts. The root `subject` retains its own account/user
intersection; `subject.subaccounts` lists 1–63 sorted, unique exact account/user
intersections. An item must match one intersection. A null user applies only
to that account. These fields are issued by Portal, not inferred at the site.

The preceding schema remains valid for self, personal, project, exact Run reads
and organization scopes without child subjects. Old versions never acquire
subtree meaning. Consumers validate the version before accepting child rows.

## Native CPU/GPU topology

The additive node fields `cpu_ids`, `cpu_topology` and `gpu_total` carry native
Slurm topology. CPU IDs are sorted unique scheduler IDs, not Linux affinity.
The optional shape has `sockets`, `cores_per_socket`, `threads_per_core`.
Configured GPU quantity supplies the positional background; only the existing
job GRES indices identify allocated positions. Unknown fields remain null.

One exact job JSON observation supplies CPU bitmap and GRES. The existing
hostlist expansion binds nodes; one additional `sinfo --json --local --Node`
read is narrowed to that verified node list. Node thread dimensions expand the
bitmap exactly as Slurm `scontrol` does. A requested thread count or allocated
CPU count is never used to guess IDs. Differing socket/core dimensions make
the CPU layer unknown. This read grants no other node, process or file access.

The canonical standard-library projection is `sai_native_slurm.py` in the
producer repository. The standalone CLI packages a byte-identical export
verified by source SHA-256, preserving local native authority without HTTP.
Web and Agent consumers receive the same allocation DTO; they do not parse
Slurm. Existing v2/v3 scope semantics and authorization remain unchanged.

At most 65,536 CPU IDs per node and 262,144 per observation are accepted.
The shape product is at most 65,536 and bounds every CPU ID. Renderers may
use compact ID ranges for large allocations without truncating JSON facts.
These additive fields also pass through placement and managed placement
wrappers. Source compatibility does not establish deployment.
