# Compute limit context v1

Status: source candidate, not deployed. This additive job field uses the typed
association Comment v2 carrier. The public DTO and native carrier have separate
version numbers. The public shape is defined by [schema.json](schema.json).

`limit_context` describes current native limits and their verified SAI policy
sources. Slurm retains the original scheduling reason. The field identifies
neither a uniquely proven trigger nor the last person to change a native value.

## Job binding and reads

The shared `read_job_contexts` reader runs after job authorization, filtering and
pagination. It reads exact job association IDs first, then the declared ancestor
IDs from v2 metadata. Both phases use native `sacctmgr --json show association`
with `WOPLimits`, deduplicating IDs into batches of at most 512. No eligible jobs
means no extra read. Local queries use the caller's Unix authority; gateway reads
retain their existing capability and service-identity boundaries.

Rows must match the job's cluster, account, user, partition and current lineage.
Ancestors must be exact account-only associations on that lineage. A source is
verified only when its managed metadata binds the current association and agrees
with the observed native value. Member metadata also binds the current user
association ID. Internal identities and manual Comment suffixes remain private.

## Public fields

| Field | Meaning |
| --- | --- |
| `observed_at` | Association observation time as Unix seconds, separate from the queue observation |
| `constraints[].account` | Native account at the observed layer |
| `constraints[].scope` | `account` or `member` |
| `constraints[].field` | `billing_tres_limit` or `max_submit_jobs` |
| `constraints[].value` | Exact unsigned decimal string, preserving native integer precision |
| `constraints[].sources` | Verified policy categories, or `[]` when provenance is unknown |

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
layer, native value, billing TRES unit or submitted-job count, and source labels.
Unknown native codes remain unchanged. Missing or mismatched metadata preserves
native numbers with unknown sources. Read failure preserves the authorized job
result and its bounded diagnostic. The separate `account_restriction` field
continues to apply only to `AssocGrpJobsLimit`; `open` emits no account notice
and does not imply a job can run.

## Migration

Compatible CLI, Read gateway, Core DTO and Lua consumers precede the Site
helper/writers, followed by Ops and the original policy projector's metadata
backfill. Numeric limits remain unchanged during backfill. The SAI helper uses
standard Slurm APIs, preserves the original manual suffix and supports both
carrier versions before v2 writes start. Slurm source, libraries and protocol
remain unmodified.

v1 remains readable only for existing or in-flight association records during
this paired migration. Remove that bridge after the original worker has migrated
the full accepted cohort. Deployment and backfill remain pending in the
[roadmap](../../../docs/roadmap.md).
