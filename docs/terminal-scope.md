# Human and Agent command scope

Decision: 2026-10-09, clarified by the user. `sai-cli` is shared by people and
agents. Cluster users need fast queries integrated with their SSH aliases;
remote agents need broader authorized query and management capabilities through
Portal. The former summary-and-cost-only interpretation is superseded.
The overloaded full-screen workbench remains retired; it is not the model for
these focused command interactions.

## Human workflow

Keep `sqm`, `sqa`, `gpu`, `cpu` and `quota` familiar and immediately usable.
The inspected shared login profile maps `sqm` through `squeue` to `stat_job`,
`sqa` to `stat_job -A` with its existing group context, `gpu` to `stat_gpu` and
`cpu` to `stat_cpu`. The quota function resolves a path's Lustre project ID and
queries its native quota. This is implementation evidence, not a universal
business definition of those scopes.

The legacy `sqa`/`ja` mapping can select a Unix group name that is not the applied
Slurm account. The shared alias migration binds those names to the existing
`_SAI_LOGIN_ACCOUNT` context, also used by the login directory/summary. It does
not repurpose Unix group variables or reinterpret an explicit CLI `-A` value.

The first integration is `sai jobs local`, with thin versioned `stat_job` and
`stat_job_all` wrappers in the shared package. It replaces shell interpolation
and positional table parsing with Slurm's JSON and the shared job presenter.
See the [native contract](../contracts/native-jobs/v1/README.md). Source support
does not by itself switch installed aliases or prove login/compute latency.

Integrate those operations with SAI command entrypoints using the existing
helpers or a single shared replacement. Preserve valid flags, self/account
selection, useful presentation and return-to-shell behavior. Establish the
actual alias behavior before redirecting it. Do not parse a human table back
into JSON or source the whole interactive login profile for each query.

Slurm client calls on a login/compute node stay in the site's native path;
Lustre quota uses the filesystem available to that user. Local observations
must not depend on obtaining a Portal capability, checking a central account
summary or reaching a public endpoint first. A cost inquiry still goes to the
business price owner. Local native permission and Portal business permission
are separate, even when the displayed account names happen to match.

## Agent workflow

An agent on a user's computer or isolated SAI user VM invokes the same CLI
operations through explicit arguments and JSON. It can query resources,
accounts, organizations/projects, tasks, costs and operations, then manage the
user's authorized Portal resources. Expose concrete existing business actions,
not an unrestricted HTTP/SQL/shell proxy or a mirror of the Portal page tree.
The surface can be broad without requiring a full-screen human navigation tree.

Use normal Identity user/delegated authorization and Portal's existing service
owners. Model choice, chat sessions and Agent orchestration belong to the
caller. CLI operation must not require Pilot Session, Pool or model-budget
activation. Hosted agents use per-user credentials, not VM-root authority or
shared platform keys. Greater command coverage does not mean greater rights.

## Shared operations, appropriate sources

| Need | Cluster-local path | Remote device or VM path |
| --- | --- | --- |
| Job queue/detail, GPU/CPU scheduler state | Existing native readers under the current identity | Authorized site reader where native access is unavailable |
| Native quota of an accessible directory | Existing Lustre/native helper, no directory scan | Authorized quota subjects through the site gateway; no assumed local path mapping |
| SAI account context, membership, budget, costs and messages | Portal domain API | Same Portal domain API |
| User-authorized Portal management | Portal mutation API and existing operation/task receipt | Same contract, independently of Pilot |

Bind source selection to the chosen operation/site and installed configuration.
Do not probe unrelated sites, silently broaden a native filter or fall back
from a remote denial to local credentials. Local and remote facts retain source,
observation time, effective scope and unsupported-field semantics. Do not label
scheduler allocation as physical utilization or native quota as purchased budget.

## Migration and acceptance

1. Reuse the observed SSH helpers for local query integration. Preserve the
   existing aliases while establishing one command/adapter implementation;
   retire replaced helper logic after its actual consumers migrate.
2. Keep existing HTTP read commands stable during that change. A new default
   local path requires explicit documentation and compatibility tests; do not
   silently reinterpret a previously remote authorized command.
3. Map Portal query/management operations to their canonical services and
   normal user scopes. Start with an existing settings workflow such as default
   account preferences, including its current site-sync receipt. Browser-only
   routes may need a paired authorization adapter; do not borrow browser cookies.
4. Validate a meaningful query and management round trip from a user device and
   dedicated VM. Reuse idempotency, version/concurrency checks, approvals and
   asynchronous states where the business action requires them. Reads never
   trigger new device login, payments, resource activation or other mutations.
5. Preserve one shared cluster publication, ordinary-user tests, native low
   latency and independently reported local/API/production acceptance.

## Delivered baseline

The existing `sai` summary, `sai status` and `sai jobs cost JOB_ID` remain valid
parts. The shared runtime uses compact human presentation and stable JSON.
The former Textual workbench is removed. Ordinary-user summary, one exact-job
estimate and a separate remote personal quota/audit read have bounded delivery
evidence in [roadmap](roadmap.md), [billing](billing-read-plane.md) and
[site reads](site-local-read-plane.md). They do not prove the newly clarified
remaining local integration or Agent management. Neither requires waiting for 3D assets
or the Pilot native UI release.
