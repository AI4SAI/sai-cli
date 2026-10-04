# Managed Run native step statistics, v1

Implemented read contract; source and local verification are separate
from deployment and live-site acceptance. CLI/TUI, console and Pilot consume
one explicit actor-owned Run read. The source is Slurm sstat under the actual
job owner's site identity, through the existing site-run helper after its
permanent privilege drop. It is not a capability-gateway privilege fallback.

The producer resolves current account/site/Run READ and derives the exact
scheduler ID, account and submission marker. Clients supply only the Run,
workspace and site, never a username, node, native command or another actor.
Compute READ does not imply file, billing or submission permission. No file
ACL, payer admission, model renewal or job mutation is performed by this read.

`available` contains one bounded observation with 1–64 unique steps. Each step
keeps its native numeric-job suffix, including batch/extern/interactive. Nodes
are that step's confirmed nodes, not every node in the job. Metrics aggregate
only over tasks of that step: average_cpu_seconds is average cumulative CPU
time (whole-second native output), average_rss_bytes is the task mean RSS
statistic, maximum_task_rss_bytes is a single-task RSS peak. These are not
instantaneous utilization, whole-job memory totals or per-node measurements.
Bytes are decimal integer strings; native formatting uses floating point, so
these are observations, not a promise of arbitrary-width exact counters.
Unset/sentinel metrics remain null; an explicit zero remains zero.
Multi-node extern step metrics also remain null: native task counts and node
coverage cannot prove that every node supplied accounting fields. Its nodes and
task count remain visible; valid single-node extern metrics can be returned.

`read_started_at`/`read_finished_at` delimit native query execution. They are
both null when no native read occurred, otherwise ordered UTC timestamps.
`sampled_at` remains null because the source does not expose a reliable sampling
timestamp. `queried_at` is the server's query time and not native sample freshness.
`execution` holds the native runtime SLUID, submission/start/resize evidence and
restart count. Before/after job and step metadata must agree with the exact
Run/owner/account/marker and every statistic row. Requeue or resize during a
read invalidates the observation; runtime SLUID alone does not rule out resize.
No paths, process IDs, scripts, UID/GID or raw diagnostic text are returned.

`not_running` and `unavailable` have null execution and no steps. Not running
means no current running-step read applies, not zero resource use or successful
completion. Unavailable means the bounded source observation could not be
established. Command exit zero does not establish success: native diagnostics,
missing/extra/duplicate steps, node coverage, unsupported fields, size and time
limits must be checked. Partial failed reads cannot become a successful empty
list. Source HTTP failure remains an error, without cached or accounting fallback.

The API is GET /v1/compute/cli/runs/{run_ref}/stats and the console's
/v1/account/compute/runs/{run_ref}/stats, with workspace_key/site_id only.
The Agent uses run_stats through run.stats, the browser uses run.stats.read.
A same-Run console link may carry view=stats, mutually exclusive with output-file
references. UI reads are explicit manual observations and discard old responses
on scope, Run, Session or mode changes. Revoked Run READ clears protected facts.

This first native reader targets Slurm 26.05.1 / data_parser v0.0.45 semantics.
Unsupported source versions fail closed. The samples are synthetic. Shared JSON
fields are allowlisted before display; unknown additive fields never confer
permission. No GPU measurements, device UUID mapping, physical placement,
whole-site telemetry, trends or additional 3D geometry are implemented here.

Paired source commits (not deployment pins):

- Portal producer: `129e08a4eadc5e23462a5e670926260640bfe2bf`.
- CLI/TUI consumer: `51875d13c60dbf22f77a3dfbe84f3d6e49aed5eb`.
- Pilot consumer: `f8882f326f69eb0636fa0ac4a0485614329cb6af`.
