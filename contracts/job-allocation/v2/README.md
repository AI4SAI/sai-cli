# Job allocation observation, v2

This replaces the v1 allocation DTO in the paired Portal, CLI and Pilot source.
The existing exact-job `jobs.allocation` capability and routes remain unchanged.
All consumers require v2; deployment must pair the gateway, Portal relay and
clients. A source migration is not a deployment or live-site verification.

## Response

`schema.json` and `sample.json` are the shared machine-readable contract and a
synthetic observation. Pilot bundles byte-identical copies. All modeled fields
are required; consumers recursively discard unknown additive fields before
validation. Beyond JSON Schema, consumers check native integer types, exact
Portal-resolved scope and subject, base/task identity (including task `0`),
first scheduler-state agreement, sorted unique node names, real UTC dates and
`stale == (age_seconds >= ttl_seconds)`. An ETag is an opaque observation digest,
not a permanent execution identity; consumers validate its hexadecimal shape,
without recomputing a digest after dropping additive fields.

| Field | Contract |
| --- | --- |
| `schema_version` | `jobs.allocation/v2` |
| `site_id`, `cluster_id`, `scope_type`, `subject` | Same resolved scope as `jobs/v1` |
| `job` | One allowlisted `jobs/v1` item; decimal base `job_id` plus nullable decimal `array_task_id` identify the requested job |
| `scheduler_states` | 1–32 native uppercase state/flag tokens, each at most 32 characters |
| `restart_count` | Native `restart_cnt`, integer 0–65535 or null when absent |
| `allocation.status` | `allocated`, `not_allocated`, or `unavailable` |
| `allocation.nodes` | Nonempty list for `allocated`, `[]` for `not_allocated`, null for `unavailable` |
| node `name`, `cpus`, `memory_mib`, `gres` | Native node name (1–128 characters), nonnegative allocated CPU integer, nonnegative allocated MiB integer or null |
| `freshness` | Existing source/UTC observation/TTL/age/stale shape; source is `scontrol` |
| `etag` | SHA-256 of authorized response facts excluding freshness and the ETag itself |

Nodes are unique, sorted by name, and limited to 4096. Zero remains zero;
unknown memory remains null. No native extra fields are forwarded. Malformed
native evidence fails with a bounded source-contract error; unavailable native
commands fail with a source error. Neither is an empty successful allocation.
Heterogeneous job-group selectors are not an allocation identity here; query
the individual component's native numeric job ID instead.

## Native evidence and limits

The supported evidence is Slurm 25.05 `data_parser/v0.0.43`
[`JOB_RES`](https://github.com/SchedMD/slurm/blob/slurm-25-05-0-1/src/plugins/data_parser/v0.0.43/parsers.c):
`job_resources.nodes.allocation[].name`, `cpus.count`, and `memory.allocated`.
The same job response's top-level `nodes` hostlist is expanded with
`scontrol show hostnames`, a native expression parser, not a node-state query.
Its set must equal the structured allocation set; disagreement is unavailable.
CPU zero alone does not imply that a node was released during job resizing.

Plain pending or terminal states have no current allocation. Multiple flags,
unresolved array aggregates, unsupported states, missing resources or empty
native allocation arrays cannot prove a current allocation and are unavailable.
The observation time is the job command's completion time; age/stale are
recomputed after name expansion. A missing observation time is an error.

## Node GRES evidence

Every node includes `gres`: null when its GRES layer is unavailable, otherwise
1–32 entries containing `name`, nullable `type`, native `count` and nullable
`indices`. Names/types are bounded identifiers; unknown additive fields are
dropped. Counts are exact nonnegative int64 values. Indices are sorted unique
nonnegative int32 values, at most 4096 per entry, and their length equals the
count. A node cannot repeat the same `(name, type)` entry.

The same Slurm 25.05 v0.0.43 job response provides `gres_detail`, an ordered
array of strings or nulls. The producer binds each entry through native
`job_resources.nodes` count/list/allocation indices and the original ordered
`scontrol show hostnames` expansion before sorting the outward nodes. Missing
or inconsistent mapping leaves GRES unknown while retaining independently
validated CPU/memory allocation. Requested TRES and whole-node flags are never
substitutes for device allocation.

Native IDX strings describe Slurm resource indices; CNT strings provide counts
without indices. Shared MPS/shard counts describe their own resource units, not
GPU cards. Their per-slot allocated/available vectors are never exposed. MIG
may also be represented as GPU GRES: neither the resource name nor its index
proves a full physical card, CUDA/NVML index, UUID, parent device or chassis slot.
No utilization, total node capacity, health or physical placement is inferred.

An empty/missing array, null entry, unsupported/malformed resource description
or an ambiguous node mapping produces null, not zero allocation. Explicit
count zero from a valid native count record remains zero. Native expansion has
whole-observation limits of 4096 entries and 65,536 expanded indices, in
addition to per-node limits, preventing compact ranges from producing
unbounded memory. Consumers reject observations exceeding either total. Source-limit overflow leaves the GRES
layer unavailable; it does not clear independently valid CPU/memory facts.

Native format evidence comes from official Slurm 25.05.0
[GRES construction](https://github.com/SchedMD/slurm/blob/slurm-25-05-0-1/src/stepmgr/gres_stepmgr.c#L1911)
and [JSON serialization](https://github.com/SchedMD/slurm/blob/slurm-25-05-0-1/src/plugins/data_parser/v0.0.43/parsers.c#L4033).
`--json` already requests detail. Format vectors based on this source are not
site samples. Current service-UID/version and native mixed/typed/shared output
require separate on-site readback.

On 2026-09-29 one running, non-array, single-node typed IDX observation from
Slurm 26.05.1 / data_parser v0.0.45 was read with an existing low-privilege site
identity and replayed successfully through this parser. The redacted fixture
preserves native field types and binding. This limited native-source check does
not establish the deployed gateway/authentication chain or coverage of shared,
count-only, array, multi-node or physical-device cases.

This is a job-scoped snapshot. Names, submit/start times and restart counts are
not permanent asset or execution-attempt IDs. Requested capacities, planned
nodes, step `used` fields, all-node load, health and physical
coordinates are not allocation evidence. No wallet, execution, inventory,
telemetry or persistence writer is added. Real-site readback remains separate from local paired producer/consumer checks.

## Browser access

Portal's browser allocation projection additionally supplies `scope_account_id`
from the same resolved authorization scope (null for self). Account-scoped Web
consumers bind it to the requested account ID alongside site/cluster/scope/job
and job/subject checks. This enables an exact deep-link read without fetching a
job list for scope metadata. The site-native DTO and its ETag remain unchanged.

The Web entry is `GET /v1/slurm/jobs/{job_id}/allocation` with the existing
site/scope/account selectors. Browser identity and current Portal membership
are resolved before issuing the same gateway capability. The broker uses only
the operator-configured `site_read_gateway_url` and bounded
`site_read_timeout_seconds`; it sends no browser credential or site-agent secret.
It requires the existing site-read issuer/signing configuration. Missing gateway
configuration is unavailable, with no fallback to the broad site-agent.

Existing Web list/detail JSON fields are preserved while their source moves to
the same gateway. Issuance is committed through the shared CLI/Web audit owner
before contacting the gateway. An upstream capability rejection is a gateway
failure, not an expired browser session. Portal authorization failures remain
403. Views clear protected results when the identity/site/session changes or
authorization is denied; missing allocation facts never become zero usage.
