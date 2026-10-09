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
  GPUs, and MIG-like GPU GRES units are not full-card counts. The additive
  `gpu.allocated_indices` field preserves the native Slurm IDX set from the
  same observation, sorted and bounded to 4096 units. Indices must be unique,
  in range and consistent with allocated counts. Missing, malformed or
  inconsistent positions are null while valid counts remain available. Zero
  allocated units have an empty set. These are scheduler positions, not a
  mapping to physical GPU serials, CUDA ordinals or measured utilization.
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

JSON remains the default machine output and imports no Rich modules. Explicit
human queries use Rich (`sai-cli[tui]`) and start with a compact partition
table. A partition name or `--details` selects node observations; GPU details
retain the partition summary. The `gpu` and
`cpu` wrappers pass `--details` by default, preserving their original dense
presentation. GPU cells preserve native IDX order: `IDX:0,3` on four units is
`[#][_][_][#]`. Unknown positions show `?`; wrapping never reorders the cells.
A down node's idle cells are red, with zero available units. The GPU partition
table retains totals, availability, allocated percentage and QOS. CPU details
show one node per row grouped by partition, with allocated/effective-total
bars for CPU and memory. Load and OS free memory remain separate and appear
at widths of 80 columns or more; narrow tables prioritize allocation ratios.
QOS appears once per CPU partition; CPU details do not repeat a summary. Long
QOS text is ellipsized; below 64 columns the GPU summary omits that column.
Exact constraints remain in JSON. Colors are terminal-only and respect `NO_COLOR` and `TERM=dumb`.
The same observation drives JSON and human output, with unchanged native calls.

Source and synthetic tests do not prove activation of shared helpers. Ordinary-
user runtime, alias, latency and native-value parity require separate checks.
