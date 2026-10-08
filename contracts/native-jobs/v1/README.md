# Local native jobs

`sai jobs local` runs one `squeue --json --local` under the caller's Unix
identity. This is a local command contract, not a Portal route or capability.
The installed native environment selects the cluster. No SAI configuration,
token, account-summary request or gateway is needed. Explicit remote connection
options are rejected; an unavailable native client never triggers an API fallback.

## Selection and presentation

```bash
sai jobs local --format table
sai jobs local -A research --format table
sai jobs local -p gpu-standard -t R,PD
sai jobs local -u alice,bob --limit 100
```

The short flags and their long forms preserve the familiar helper's semantics:
`-A/--account/--accounts`, `-u/--user/--users`, `-p/--partition`, `-q/--qos`,
`-t/--states/--status`. No filters means the effective Unix user, resolved by
UID rather than `USER` or `LOGNAME`. An explicit account, partition, QOS or state
filter selects matching jobs visible through native Slurm; it does not also
implicitly narrow to the caller. `-u '*'` explicitly omits the user filter.
This is native visibility, not evidence of Portal membership or business rights.
`SQUEUE_*` environment defaults are removed so they cannot silently change the
declared query. Native Slurm configuration is retained; SAI credentials are not
passed to the subprocess. Values are argv elements, never shell source.

JSON is the default; human tables and JSON use the same normalized observation.
There is no default row truncation. Explicit `--limit` (1–100000) reports
`has_more`; no cursor or cached snapshot is implied. The native process has a
10-second default deadline, adjustable with `--timeout` before or after the
command, at most 120 seconds. Stdout is bounded to 32 MiB, diagnostics to 64 KiB.
Oversized results require narrower filters. Malformed rows fail the read rather
than disappearing from a successful queue.

## JSON envelope

| Field | Meaning |
| --- | --- |
| `schema_version` | `native.jobs/v1` |
| `source`, `authority` | `squeue`, `native` |
| `cluster` | Cluster reported by Slurm, not an inferred Portal site |
| `actor` | Effective Unix `uid` and NSS `user` |
| `filters` | Effective nullable `users`, `accounts`, `partition`, `qos`, `states` |
| `observed_at` | UTC observation completion time |
| `items`, `count` | Allowlisted job rows and number returned |
| `has_more` | Explicit limit omitted matching rows |
| `warning_count` | Native warning count; raw diagnostics are not exposed |

Rows reuse the client `JobItem` field names and validation: job/array identity,
name, native user/account, state, priority, submit/start times, elapsed/wait
seconds, partition, QOS, nodes, slots, per-node GPU request, memory request and
reason/nodelist. Unknown values remain null. Extra native script, environment,
command and filesystem-path fields are discarded.

`job_id` is the decimal array base when present, otherwise the native job ID.
`array_task_id` preserves task zero and may contain a bracketed native array
range for a grouped pending row. It must not be mistaken for an exact remote
allocation or managed-Run selector. `state` uses existing short names for known
states; unknown states remain visible. `state_label` retains all native state
tokens. Control characters in native display text are escaped as printable
text before either presentation; malformed Unicode is rejected.

Pending `start_time` is not promoted from a scheduler forecast into an actual
start; its wait is measured from submission. Running/suspended duration follows
native start/suspend/previous-active-time fields. Missing or inconsistent timing
remains unknown. Times are UTC. `slots` preserves the helper's convention of
pending requested tasks and otherwise CPU slots. `gpus_per_node` is the native
per-node request, including typed GPU requests; MPS/shards are not physical GPU
counts. `mem_per_unit` labels CPU, node or GPU request units explicitly.
None of these observations is measured utilization or a financial fact.

`errors` from Slurm, a nonzero exit, timeout, missing client, malformed response
or oversized output is a bounded failure with no successful stdout. A valid
empty queue remains empty; Slurm's usual "Zero jobs to dump" warning is counted.
Local query support is tested separately from shared helper activation and
ordinary-user live acceptance.
