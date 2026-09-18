# Slurm Job Submit Policy

Status: implemented artifact and local Lua tests; not deployed or live-validated

## Purpose

`site/slurm/job_submit.lua` moves a small set of SAI GPU submission checks from
late TaskProlog cancellation to immediate controller-side feedback. It also
selects the Slurm account implied by a canonical submission directory using a
controller-local projection produced from control-plane facts.

This is a site artifact carried by the `sai-cli` repository. It is not a CLI
job-submission command, a scheduler, or an authorization source. The control
plane remains authoritative for users, memberships, site access, account
ownership, project shape, and policy versions. Native Slurm associations remain
the final authorization boundary for account use.

## Why This Is Separate From The Local Read Gateway

The future site-local read gateway serves `sai-cli` and TUI refreshes over a
Unix socket after verifying short-lived capabilities. It may tolerate bounded
source latency, partial results, short caches, and stale display states.

`job_submit/lua` executes inside `slurmctld`. Slurm 26.05.1 serializes calls
through a Lua mutex while controller locks may be held. A synchronous Unix
socket call would therefore turn daemon restarts, queueing, garbage collection,
cache misses, and timeout tails into scheduler-wide submission stalls. Unix
sockets remove network routing but not that failure domain.

The two paths share control-plane projections, not a synchronous dependency:

```text
control plane
  +-- signed capabilities --> site-local read gateway --> sai-cli / TUI
  +-- versioned GPU rules --> local Lua policy file --> job_submit.lua
```

The privileged password `authn-relay` is a third, separate service. Its reset
credential and failure domain must never be exposed to the CLI, read gateway,
or controller plugin.

## Submission Rules

The submit hook applies these rules only when a GPU TRES is requested:

1. Reject explicit `--cpus-per-task` and `--cpus-per-gpu`.
2. Reject explicit `--mem`, `--mem-per-cpu`, and `--mem-per-gpu`.
3. Require a per-node GPU request. Slurm may encode `--gpus-per-node` or an
   equivalent `--gres=gpu...` request in `tres_per_node`; the hook cannot
   recover which equivalent CLI spelling produced that field.
4. Require the summed GPU count per node to be divisible by the projected
   site multiple unless the effective explicit/default QOS is in the projected
   exemption set.
5. Retain an explicit account; otherwise select the account from canonical
   `work_dir`, then the Slurm default. Return a warning on a mismatch or an
   unresolved directory, and reject when no account is available.

CPU-only jobs are not affected by the CPU or memory override checks. The first
version deliberately does not reject `--mincpus`, topology fields,
`--overcommit`, or every option that can indirectly influence CPU placement.
Adding those fields requires source validation and an explicit policy change;
they must not be inferred from the current checks.

## Submit Policy Is Not Runtime Placement

This hook decides whether Slurm may accept a resource shape and which account
the submission directory implies. It does not generate Open MPI rank maps,
inspect an allocated cpuset, change CPU binding, or repair site runtime scripts
such as `/opt/sai_config`.

An earlier seven-GPU allocation on a dual-socket eight-GPU node exposed this
boundary: Slurm allocated the requested GPUs and CPUs, but the generated
`ppr:7:node:pe=3` Open MPI mapping could not keep every rank inside one CPU
package. That was a topology-correctness defect in the post-allocation mapping
logic, not an account, authentication, or submit-hook failure. Disabling
binding would hide the defect and is not the platform fix.

The submit hook must not reject an otherwise permitted odd GPU shape merely to
mask a downstream mapper bug. Every shape accepted through an exempt QOS still
needs a separate runtime-placement regression on each relevant CPU/GPU
topology. If a site intentionally cannot support a shape, that must become an
explicit projected submission policy with an immediate user diagnostic.

## Account Projection

The plugin derives only from the canonical absolute path. It does not load an
account relation cache and does not resolve Home symlinks:

| Work directory | Derived account |
| --- | --- |
| `/home/<user>` or `/home/<user>/<subpath>` | `private-<user>` |
| `/org/<org>` or `/org/<org>/<user>` | `<org>` |
| `/org/<org>/share` or `/org/<org>/shr-<folder>` | `<org>` |
| `/org/<org>/proj-<project>` or a descendant | `proj-<project>` |

Only a direct child of `/org/<org>/` whose name starts with `proj-` is treated
as a project account. This relies on Portal's naming contract: shared folders
use `shr-*`, Slurm-backed projects use globally unique `proj-*`, and personal
Unix usernames cannot use account prefixes. An unknown `proj-*` root is still a
syntactic candidate; native Slurm association checks remain the authorization
boundary.

The retired `/home/<user>/workdir_<org>` alias is unresolved. Relative paths,
repeated separators, `.` or `..`, another user's home path, and malformed
absolute paths are unresolved.

Account precedence is fixed:

1. An explicit account is retained; a path mismatch emits a warning.
2. Without an explicit account, a resolved path account is selected; a mismatch
   with Slurm's default account emits a warning.
3. An unresolved path keeps Slurm's default account when one exists.
4. A submission with no explicit, path-derived, or default account is rejected.

The controller must not call `realpath` or touch shared storage during job
submission. This is an account-selection policy and usability guard, not proof
of filesystem ownership.

## Projection Contract

The control-plane producer emits strict JSON with this shape:

```json
{
  "schema_version": 3,
  "revision": "opaque-revision",
  "generated_at": 1785823200,
  "gpu_policy": {
    "per_node_multiple": 4,
    "exempt_qos": ["gpu-special"]
  }
}
```

`scripts/render_job_submit_policy.py` validates the GPU policy fields, renders
a Lua table, and replaces the output atomically. It does not read Portal
databases or infer memberships. Portal owns the authoritative naming and
association facts; the controller uses native Slurm authorization after the
lexical path decision.

Schema 3 is release configuration, like `slurm.conf`, rather than a short-lived
authorization grant. It contains no account or membership cache and has no
renewal timer. Portal's canonical QOS catalog produces a revision; an operator
publishes that validated revision together with the native QOS readback. QOS
rule changes require the same coordinated release. Native Slurm associations
and limits remain authoritative on every submission.

The obsolete expiring schema 2 is rejected. A missing or malformed policy file
rejects the new Lua revision at load time instead of selecting guessed rules;
Slurm retains its previous valid Lua state on a failed reload. Validate the
first installation before enabling the plugin. Ordinary publisher downtime
does not change a running, already approved site policy.

## Hot-Path Budget

The Lua state loads the GPU policy snapshot once through `dofile`.
`slurm_job_submit` performs only bounded string checks, direct account
construction and integer arithmetic. It
performs no file read, network request,
DNS lookup, subprocess, module load, logging RPC, or filesystem metadata query.

Warnings use `slurm.user_msg`, which Slurm propagates even when the hook returns
success. Rejections return a bounded Slurm accounting/GRES error plus the
specific user message.

The modify hook prevents non-root callers from changing account, QOS, CPU,
memory, or GPU-shape fields after submission. Name and other non-policy updates
remain available. This closes the immediate `scontrol update` bypass without
attempting to reconstruct every array-job modification state.

## Deployment And Reload

The controller-local target layout is:

```text
/etc/slurm/job_submit.lua
/etc/slurm/sai/job_submit_policy.lua
```

First enablement or removal of `JobSubmitPlugins=lua` requires a planned
controller restart. Subsequent script updates use Slurm's built-in reload path.
Slurm checks only the main `job_submit.lua` modification time on each call, so
the safe update order is:

1. Render and validate the JSON projection outside the submission path.
2. Atomically replace `job_submit_policy.lua` on every active/standby controller.
3. Atomically install the reviewed main script, or advance its mtime to a value
   strictly greater than the previous value so Slurm reloads the Lua state.
4. Submit bounded positive and negative canaries and read controller logs.

A failed reload retains the previous valid Lua state when one exists. Keep the
previous main script and snapshot as one rollback pair; restore the snapshot
first and then advance the restored main script's mtime. Controller failover
must not expose a different revision.

Do not update the snapshot in place, place it on shared user storage, or trigger
reload before all controller-local files are durable.

## Validation Gates

Repository validation:

```bash
.venv/bin/python -m pytest tests/test_job_submit_lua.py \
  tests/test_job_submit_policy_renderer.py
python3 scripts/check_public_surface.py
```

The tests execute the actual Lua script through `liblua`, cover typed GPU TRES,
QOS exemption, every blocked CPU/memory field, account forcing, standard and
account-bearing projects, home aliases, suspicious paths, invalid policy loads, and
modify bypasses. Static guards prove that the submit callback contains no
runtime external I/O.

Before production enablement, run all of these separately:

- Slurm-version compatibility on a matching disposable controller config.
- At least ten times the observed peak submission rate, with no more than five
  percent throughput regression and no new long-tail controller stalls.
- `sbatch`, `salloc`, `srun`, array, heterogeneous-job, explicit/default QOS,
  typed/untyped GPU, and proxy-submission canaries.
- Account association positive and negative cases plus invalid policy files,
  malformed reload, publisher outage, and controller failover.
- Runtime placement for every accepted per-node GPU shape on each relevant
  topology, including odd and near-full shapes on multi-package nodes.
- TaskProlog observation-only overlap, followed by removal only after equivalent
  submit-time evidence is complete.

Local tests do not prove live `slurmctld`, accounting associations, QOS,
controller failover, GPU allocation, TaskProlog removal, or production latency.

## Upstream Evidence

The implementation is pinned to the Slurm 26.05.1 Lua contract. The relevant
upstream sources are `src/plugins/job_submit/lua/job_submit_lua.c`,
`src/lua/slurm_lua.c`, `src/common/slurm_opt.c`, and the official
`job_submit_plugins.html` documentation. Revalidate these fields before a Slurm
minor-version upgrade.
