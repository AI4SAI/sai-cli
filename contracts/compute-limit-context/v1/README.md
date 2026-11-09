# Compute limit context v1

This additive job field uses the typed association Comment v2 carrier. The public
DTO and native carrier have separate version numbers. The public shape is defined
by [schema.json](schema.json). The applied-record extension requires paired
reader and writer deployment before metadata is refreshed.

`limit_context` describes native member limits and the account limits and policy
sources last verified by the site writer. Slurm retains the original scheduling reason. The field identifies
neither a uniquely proven trigger nor the last person to change a native value.

## Job binding and reads

The shared `read_job_contexts` reader runs after job authorization, filtering and
pagination. It reads exact job association IDs using native `sacctmgr --json show
association` with `WOPLimits`, deduplicating IDs into batches of at most 512.
The optional v2 `applied` record contains the writer's bounded parent observations,
target association and lineage, source revisions, and actual recording time.
Readers use that record without querying parents that ordinary users may not
be allowed to see. The gateway uses the same record even when it could read more.
Existing v2 records without `applied` retain the two-phase ancestor read during
migration. No eligible jobs
means no extra read. Local queries use the caller's Unix authority; gateway reads
retain their existing capability and service-identity boundaries.

Rows must match the job's cluster, account, user, partition and current lineage.
Recorded ancestors must be exact account-only associations on that lineage.
The writer verifies each source against the native value before recording it.
A contradictory applied record is not replaced by a broader parent query.
Member metadata also binds the current user
association ID. Internal identities and manual Comment suffixes remain private.
Seeing another user's job does not imply that its association is readable.
If that association is unavailable, its native reason remains without attribution.

## Public fields

| Field | Meaning |
| --- | --- |
| `observed_at` | Association observation time as Unix seconds, separate from the queue observation |
| `basis` | Optional `applied_record` when account constraints come from the writer's record |
| `recorded_at` | With `basis`, the actual account-record time, distinct from this query's time |
| `constraints[].account` | Native account at the observed layer |
| `constraints[].scope` | `account` or `member` |
| `constraints[].field` | `billing_tres_limit` or `max_submit_jobs` |
| `constraints[].value` | Exact unsigned decimal string, preserving native integer precision |
| `constraints[].sources` | Verified policy categories, or `[]` when provenance is unknown |

Member values still come from the current user-association observation. A result
containing only a member constraint has no parent-record time. External native
changes not yet reconciled by the writer do not turn a recorded account value
into a freshly verified value.

Source objects contain an allowlisted `kind` and, where present, a validated
`service_level_code` or `grant_kind`. Kinds are `service_level`, `grant`,
`reservation`, `org_admin`, `project_pi`, `hard_clamp`, `member_limit` and
`risk_control`. They contain no free text, person, wallet, order or internal
owner reference. Entitlements and reservations contribute to one entitlement
capacity; equal-valued clamps remain distinct policy constraints.

The applicable pending native reasons are:

| Native reason | Context field and interpretation |
| --- | --- |
| `AssocGrpBilling` | `billing_tres_limit`, with account and member group billing layers kept separate |
| `AssocMaxSubmitJobLimit` | `max_submit_jobs`, using the member's explicit value or nearest explicit ancestor |

Group billing capacity is shared at its own layer and is not the minimum of
per-member allocations. `MaxSubmitJobs` inherits from the nearest explicit
layer; more distant values are overridden. An unverified nearest source remains
unknown, and a missing nearer row cannot establish a farther inherited limit.
`AssociationJobLimit` and `AssocGrpSubmitJobsLimit` have different native meanings.
QOS reasons and running jobs receive no association-source context.

Lists keep their short native reason labels. Details add the account/member
layer, value, billing TRES unit or submitted-job count, source labels and, for
recorded account constraints, the record time.
Unknown native codes remain unchanged. Missing or mismatched metadata preserves
native numbers with unknown sources. Read failure preserves the authorized job
result and its bounded diagnostic. The separate `account_restriction` field
continues to apply only to `AssocGrpJobsLimit`; `open` emits no account notice
and does not imply a job can run.

## Migration

Compatible CLI, Read gateway and Core DTO consumers precede Site writers for the
optional `applied` payload. The v2 frame, SAI native helper and Lua reader are
unchanged. The original policy projector and workers refresh metadata while
numeric limits remain unchanged. The SAI helper uses
standard Slurm APIs, preserves the original manual suffix and supports both
carrier versions before v2 writes start. Slurm source, libraries and protocol
remain unmodified.

v1 remains readable only for existing or in-flight association records during
this paired migration. Remove that bridge after the original worker has migrated
the full accepted cohort. Applied-record activation and backfill are tracked in the
[roadmap](../../../docs/roadmap.md).
