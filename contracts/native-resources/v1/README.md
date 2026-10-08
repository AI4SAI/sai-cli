# Native resource observations

`sai resources local` executes one `sinfo --json --local --Node` as the current
Unix user. `gpu`/`stat_gpu` and `cpu`/`stat_cpu` can use the same versioned CLI
implementation. No Portal configuration, token, gateway, host SSH fanout or
background sampler is involved. This is scheduler information, not a hardware
inventory, commercial catalog, eligibility decision or GPU utilization sensor.

```bash
sai resources local --kind gpu --format table
sai resources local gpu-example --kind gpu --format table
sai resources local --kind cpu --details --format table
sai resources local --node 'compute-[01-02]'
```

The optional positional partition preserves existing helper usage. `-p` names
the same native partition filter; `-n/--node` passes a hostlist to Slurm without
client expansion. Explicit remote connection options are rejected. The installed
native environment owns cluster selection and access. `SINFO_*` presentation/
filter defaults and SAI credentials are not passed to the native process.

`--kind gpu` selects nodes with configured GPU GRES units; `--kind cpu` selects
nodes with no configured GPU GRES, not a promise that the hardware has no GPU.
There is no site-specific partition whitelist. Unknown GPU configuration is
reported separately as `unclassified_nodes`; `--kind all` retains those nodes.
This coverage must be considered before treating a filtered subtotal as complete.

## Source and quantities

Per-node mode must yield one node per native record. Group averages are not
expanded into fabricated node measurements. Duplicate node/partition records
must agree. Each node appears once in global totals, even when it belongs to
multiple partitions; partition totals can overlap.

- GPU figures are configured and allocated GRES quantities. Typed entries are
  combined without double-counting a generic total. MPS/shards are not physical
  GPUs, and MIG-like GPU GRES units are not full-card counts. Allocation indices
  are not used to reconstruct physical device usage or identity.
- CPU JSON preserves native total/allocated/idle/other counts and the reserved
  CPU count. Effective total and idle capacity exclude the native CPU-ID
  specialization set. Counting that bounded set does not infer CPU topology.
- Memory keeps configured, reserved and allocated MiB separately. Effective
  capacity and unallocated memory exclude native reserved memory. These are
  scheduler quantities, independently of reported free operating-system memory.
- `reported.cpu_load_hundredths` is a reported load average, not CPU utilization
  percent. `reported.free_memory_mib` is the node's last report. `sampled_at` is
  null because this source does not supply a sensor sample time. Down or
  unresponsive nodes do not expose stale report values as current measurements.

`free_on_ready_nodes` counts unallocated effective resources on nodes and
partitions without an observed blocking state. It does not account for every
reservation, QOS, account permission, topology or co-resource constraint, and
does not promise a job can start. Down/draining/inactive capacity is separate
from allocated capacity; it is never turned into a utilization percentage.
Unknown quantities/states remain null; they do not become free resources or zero
measurements. Malformed native responses fail with a bounded diagnostic.

## Machine and human output

The `native.resources/v1` JSON envelope has `source=sinfo`, `authority=native`,
`observation_kind=scheduler`, cluster, effective UID/user, observation time,
explicit filters, nodes, partitions, a deduplicated summary, unclassified-node
count and warning count. Nodes retain states, native kinds, partition names,
GPU/CPU/memory quantities and reported observations. Partitions expose their
native state and allow/deny/assigned QOS constraints; these are not the caller's
personal QOS permissions. Native addresses, comments, reasons, account/group
lists, billing weights and unrelated provider fields are discarded.

JSON remains the default machine output. Human output starts with partition
summaries, including the largest free amount on one node; totals on different
nodes do not establish that one job fits. A partition name or `--details`
expands node observations. Counts and readable memory sizes replace simulated
device matrices and misleading usage bars. The same observation drives both
presentations. Native deadline and byte limits are shared with local job reads.

Source and synthetic tests do not prove activation of shared helpers. Ordinary-
user runtime, alias, latency and native-value parity require separate checks.
