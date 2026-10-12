# Human and Agent command scope

Decision: 2026-10-09, clarified by the user. `sai-cli` is shared by people and
agents. Cluster users need fast queries integrated with their SSH aliases;
remote agents need broader authorized query and management capabilities through
Portal. The former summary-and-cost-only interpretation is superseded.
The overloaded full-screen workbench remains retired; it is not the model for
these focused command interactions.

## Query usability correction

Native job account selection now discovers this Unix user's other Slurm
associations through `account local`, sharing the existing parser. The selector
loads on opening and keeps the initial queue independent. Quota offers a native
directory chooser; it does not invent an account-to-path mapping. Selections
survive switching queries, without changing shell or saved defaults.

Selected jobs show node/pending-reason context directly. Enter gives the
allocation detail keyboard focus; arrows/page keys scroll, `r` refreshes that
detail and Escape restores the selected list row. The published alpha displayed
numbered GPU grids and per-thread CPU panels. Those were scheduler allocation
maps; the user rejected their readability and missing physical connections.
The interconnect correction below supersedes that presentation in the shared
runtime. Resource selection preserves its existing allocation colors.

This slice is included in the portable `0.2.0a1` alpha. Shared source
`d49be4d3ec77` was deployed on 2026-10-12 after an ordinary-user canary. All 962
runtime files and permissions matched the archive; nine UI dependencies,
connection configuration and login profile remained unchanged.

The ordinary user's candidate and stable-entry checks discovered six native
accounts, selected another identity, matched a running job's CPU IDs to Slurm,
inspected the numbered GPU/CPU map at 100 and 40 columns, refreshed and returned
to the same row, and selected another real directory for Lustre quota. Existing
business authorization, account choices and `sqa`/`sqm` also worked. A real PTY
exited normally and restored terminal settings. One compute node read the same
shared version, native accounts/jobs and quota under that ordinary UID, launched
by the operator; no node installation or configuration change was needed.

Source checks passed 1209 tests and hosted Python 3.11/3.13 CI. The previous
runtime and guarded rollback remain; rollback was not exercised. Staging and
operator connections were closed. This is bounded site verification, not fleet
or human visual acceptance. These checks did not include a CPU-only running job;
no job or authorization grant was created for the check.

## Human workflow

Keep `sqm`, `sqa`, `gpu`, `cpu` and `quota` familiar and immediately usable.
The shared login profile maps `sqm` through `squeue` to `stat_job`, and `sqa`/`ja`
to `stat_job -A ... --with-subaccounts` with the applied Slurm account.
The identity queue includes native child-project accounts; explicit `-A` without
that option remains exact. `gpu`/`cpu` use the common native
resource reader; `quota` delegates to the same CLI's path-to-project Lustre read.
These are native scopes, not business ownership.

The shared alias migration replaced the unrelated Unix group selector with the
`_SAI_LOGIN_ACCOUNT` context, also used by the login directory/summary. It does
not repurpose Unix group variables or reinterpret an explicit CLI `-A` value.
A root-account-only alias missed jobs charged to child projects. The native
subtree option corrects that identity scope using Slurm `WithSubAccounts` and
Lineage. The alias update takes effect when the shared profile is reloaded or a
new login shell starts. The 2026-10-09 shared publication of source `f92698a3ce8e`
passed positive ordinary-user organization and project reads on a login and a
compute node, plus the actual `sqa`/`ja` aliases in an interactive login shell.
The paired profile change only adds `--with-subaccounts` to those two aliases.
No saved default, directory, membership or scheduler data changes. Existing
shells load the new alias with `source /opt/sai/shell/bash.profile`.

The first integration is `sai jobs local`, with thin versioned `stat_job` and
`stat_job_all` wrappers in the shared package. It replaces shell interpolation
and positional table parsing with Slurm's JSON and the shared job presenter.
See the [native contract](../contracts/native-jobs/v1/README.md). Source support
does not by itself switch installed aliases or prove login/compute latency.

## Local job delivery

On 2026-10-09, CLI source `7c7e4a9b5a2e` and the shared alias migration
`92fa9fcf61be` were deployed once through the existing shared publication.
The selected 578-file runtime passed content/permission checks; the existing
connection configuration stayed unchanged. Both old job scripts now delegate
to the same versioned implementation. New shells load the corrected account
aliases; already-open shells retain their definitions until reloaded.

An ordinary user on one login and one compute node read their empty queue and
a separately selected native-visible running-account sample. IDs/scopes matched
native Slurm; tables, JSON, both packaged wrappers and actual SSH-shell aliases
passed. The login had no Identity device session, while native reads succeeded.
This does not establish a new authenticated Portal session or an owned running
job. Slurm 26.05.1/data parser v0.0.45 and Python 3.12.3 were exercised.

Five bounded samples gave median CLI times of 86/98 ms on the two nodes, versus
44/42 ms for the legacy helper. Removing unrelated remote startup dependencies
reduced the first candidate's 172/182 ms. These are observations, not a fleet
performance guarantee. The source passed 970 tests; the installed runtime passed
80 HTTP/native/auth/cost checks. The shell migration also passed its focused
context tests. Prior runtime, exact helper/profile backups and paired rollback
were retained; rollback was not exercised. Temporary canaries and the unselected
candidate were removed. General Agent management remains unfinished.

## Local resource delivery

Source `26f118f7ae77` was published through the same shared runtime on
2026-10-09. `gpu`/`cpu` retain their names and positional partition selection;
their old script bodies were replaced by thin versioned wrappers. No node
package, mount, profile or connection-configuration update was needed.

The default is now a partition overview, with node details on an explicit
partition or `--details`. Allocated, free and blocked resources remain separate;
GPU figures are Slurm GRES units rather than measured utilization or attested
physical cards. CPU/memory capacity excludes native reservations. Host load and
free-memory reports keep their separate meaning and unknown values. Human
missing-session output is a short sign-in hint; JSON and authentication failure
exit codes are unchanged.

The 582-file runtime passed content/permission readback. Source checks passed
1011 tests and 124 installed-wheel checks. An ordinary user on a login node and
one compute node matched the native node set and cross-checked effective CPU,
configured memory and GPU quantities with `scontrol`; both wrapper modes,
partition selection, summaries/details and actual login aliases passed. Existing
`sqm`/`sqa` and applied-account context also passed after selection.

Five local-query samples gave median whole-CLI times of 113/124 ms on the two
nodes; native `sinfo` was about 42/36 ms and the old helpers about 40–44 ms.
This is a bounded one-site observation, not a fleet latency or human product
acceptance claim. Old runtime/helper backups and conditional rollback were
retained, without a rollback exercise. Temporary probes/uploads were removed.
Neither these checks nor scheduler counts establish actual GPU utilization,
hardware identity, user job eligibility or new Portal management authority.

## Local quota delivery

Source `f04459c2c5c9` and its thin shared `quota` function were published on
2026-10-09. The function keeps the current-directory default and one quoted path;
Agent calls use `storage local-quota` JSON. Two native reads resolve the path's
project ID and request exact counter/grace fields from `lfs`; no gateway or Portal
device session is needed. Existing job/resource entries remain on the same shared
runtime. New shells load the function; existing shells retain their definition.

The 583-file runtime and exact profile change passed content/mode readback.
1038 source tests and 135 installed-wheel checks passed, including valid unusual
filenames, native-byte paths, failed/inaccurate reads and shell argument handling.
An ordinary user on a login node and one compute node matched Home and working-
directory counters/limits against native `lfs quota`; actual `quota`, explicit
path, unassigned-path failure and existing job aliases were checked after
selection. Five query samples gave medians of 63/60 ms. This is bounded
Lustre 2.17.0/site evidence, not fleet, enforcement or human-product acceptance.

The result names its whole filesystem-project scope. It does not turn a shared
project total into personal/subtree usage, a Portal budget or physical disk
headroom. No quota, user data, identity session, job or service was changed for
acceptance. Old runtime/profile and paired rollback were retained; rollback was
not exercised. Probes/uploads and temporary shared canary were removed.

## Local execution

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
3. Continue the [default-account management action](portal-management.md), now
   implemented in source with normal user scopes, the existing preference writer
   and site receipts. Pair its release and acceptance before broadening domain
   coverage. Authentication adapters must not borrow browser cookies.
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

## Focused interaction correction, 2026-10-10

The user rejected replacing all TUI interaction with a static summary. Retiring
the broad workbench did not authorize losing useful keyboard selection.
`sai tui` now presents the native job/resource/quota queries and optional account
read in one compact surface. It shares alias readers and resource renderables.
No mandatory account/project/job/partition ID entry, new page tree, file manager,
Pilot orchestration or backend fact source is introduced. `status` and the login
summary remain one-shot. Native reads work without OAuth or Portal connectivity;
explicit account/cost reads retain normal authorization and exact job binding.

The focused interaction was deployed from `f915ecf0cec0` on 2026-10-10.
Focused keyboard tests cover immediate responses,
scope changes, denied/reused-job cost, missing optional packages and cancellation
of a blocked native child. Source and installed-wheel PTY checks preserve terminal
settings on exit; 40/100-column synthetic views have been inspected. The full suite passed 1105 tests; wheel/sdist builds, public-surface checks and
installed-wheel PTY restoration passed. Ordinary-user shared publication and selected-entry readback also passed.
No human usability acceptance is claimed.

The new code is a Textual presentation over existing commands: it adds no business
route, native parser, scheduler write or account mutation. The size increase covers
the real interaction and cancelable process boundary removed by the static alias;
independent review found and closed stale-widget, revoked-cost and managed-config
regressions. The original authentication setup is retained.

The 945-file shared runtime was selected once, with original connection config
and login profile hashes unchanged. An ordinary user on a login node exercised
435 candidate and 439 later selected identity jobs, job details and exact cost,
GPU/CPU views, partition selection, native quota, account discovery and a
40-column layout. The normal shared command entered and exited a real PTY,
restoring its terminal settings. These changing counts are separate live queue
observations. No job, membership, quota or account preference was changed.
This is one login-node runtime check, not fleet or human usability acceptance.
The old shared release remains available for rollback; task staging and the
readback helper were archived/removed and all operator sessions closed.

## Per-job topology

Enter on an exact native job now reads its allocated nodes, GPU IDX positions
and CPU IDs using the shared projection. Pending grouped arrays retain a concise
no-allocation detail. `jobs local --job-id ID` exposes the same observation as
JSON or a compact Rich map. CPU partitions add Slurm socket/core/thread dimensions
from their existing node read. The current slice does not change refresh policy
or account selection; those user feedback items follow its delivery.

Shared runtime `e27c47495390` and the gateway producer `ead4d38f6d66` were
published on 2026-10-11. The 954-file client inventory, permissions, original
profile/configuration and standard-user selected-entry checks passed. Four
native samples matched Slurm CPU_IDs; an authorized remote allocation matched
the local observation, and a real native TUI selection displayed GPU/CPU IDs.
The gateway's original dependency runtime and seven protected inputs were
unchanged; journal start/finish pairs and active/enabled state were checked.
Old packages/releases are retained for rollback. Task staging and all operator
connections were closed. Web/Pilot source is merged and awaits its original
owner's compatible production release. This is bounded site verification,
not a whole-product or fleet acceptance claim.

### Topology readability correction

The initial dot/core bitmap was rejected as unreadable. The current renderer
leads with the exact allocated GPU/CPU numbers, names CPU socket groups and
shows their numbered ranges. Highlighted ranges belong to this job; other
ranges do not imply idle capacity. Rich Panels/Columns handle wrapping without
a custom terminal framework. Native parsing and the shared Web/Agent DTO are
unchanged. Refresh/account-selector feedback remains queued separately.

Shared CLI `d9695900cd7a` was published on 2026-10-11. An ordinary user selected
a real running job through the installed 100-column TUI, showing the numbered
allocation and socket groups. The 954-file inventory, permissions and original
profile/configuration hashes passed readback. Source tests passed 1159 checks,
including hosted Python 3.11/3.13 CI; synthetic views covered 40/80/100 columns.
The previous shared runtime remains available for rollback; staging was archived
or removed and both SSH/SFTP pairs closed. The Web presentation correction is
merged but still follows its original owner's production release. The gateway
and native DTO did not change in this display-only publication. These checks
do not constitute the user's visual acceptance.

### Interconnect correction, 2026-10-12

The numbered CPU/GPU layout was a scheduler allocation map, not an interconnect
view. The contract `node.interconnect/v1` keeps one fact source for
CLI/TUI, site gateway, Web and Pilot. It records verified CPU/NUMA-to-GPU
relationships, the complete GPU path matrix and safe node-fabric peers with an
observation interval. The compact renderer gives those relationships visual
priority and keeps exact thread IDs in one bounded range line. It does not infer
edges from index order, GPU model, hostname or a count.

The producer reads native NVIDIA, Slurm GRES, Linux NUMA and site fabric
evidence during a bounded operator publication. Readers use the existing
root-published runtime path or authorized gateway projection; they do not SSH to
nodes or execute `slurmd -G` on every refresh.

Shared CLI `8f165a8637db` and the paired read gateway `27c312e593b5` were
published on 2026-10-12 with root-owned, time-bound records. The optional native
Slurm-to-Linux CPU map now highlights the job's CPU allocation on NUMA rows;
exact Linux IDs appear on expansion. GPU summaries include only the selected
devices. Counts, sparse IDs and package groups come from the record, without
machine-model layout branches. Mapping validity uses the stable Slurm daemon
start time; the recomputed machine boot-time estimate is observation metadata.

Ordinary-user candidate and selected-entry checks passed local/API allocation
and interconnect equality, CPU locality, real native TUI at 40/100 columns and
terminal restoration. The shared runtime's 964 files and permissions matched;
nine UI dependencies, connection configuration and login profile were unchanged.
The real gateway UID read all published records, and its current process journal
contained paired successful allocation reads. Native observations cover CPU-only
and multiple GPU configurations; this user check exercised a running GPU job.

Some registered nodes still have no current record or CPU mapping. Their
relationships remain unknown. Prior programs and hardware records remain
rollback inputs; test staging and the unused intermediate runtime were removed.
The source suite passed 1215 tests and Python 3.11/3.13 CI. This is bounded live
evidence, not human visual acceptance or multi-node job acceptance. Web/Pilot
interconnect adoption remains with its existing release owner.

Shared client `62adfb627112` followed on 2026-10-13. CPU tables and both node
detail views now identify scheduler dimensions as Slurm groups, avoiding a
physical-socket claim. Periodic callbacks also stop when Textual begins shutdown;
a deterministic regression reproduced the former access to removed widgets.
Python 3.11/3.13 CI, ordinary-user candidate and selected CPU/GPU views at
40/100 columns, and real-terminal exit/restoration passed. The 964-file runtime
was verified with configuration and dependencies unchanged; prior runtime and
rollback remain, while test staging and operator sessions were cleaned up.

## Focused query interaction

The current source adds automatic refresh of the visible view: jobs every 5
seconds, GPU/CPU every 10 seconds, quota every 30 seconds and accounts every 60
seconds. `p` pauses/resumes; `r` refreshes immediately. An open selector or job
detail suspends polling. Reads remain serialized and bounded. Lists retain
selection, scroll and focus; failures clear stale facts. Removing a selected
partition does not silently expand its scope to every partition.

Enter or a click on a CPU/GPU node opens inline details from that same native
observation, including reported load/memory and known CPU dimensions or GPU
indices. It adds no query, node SSH or measured-utilization claim. The existing
Rich allocation bars and native GPU position renderer are reused.

The account view loads one authorized selector directly, replacing the separate
load button. Its label names the account being viewed. Each refresh uses the
existing directory and overview GETs; a changed choice clears old account facts.
It does not change the saved default, shell identity, payer or working directory.

Source `053ffffc2ea8` was published on 2026-10-11 through the existing shared
runtime. Its 955 files and permissions passed exact readback; configuration and
login-profile hashes stayed unchanged. Ordinary-user candidate and selected
checks exercised the actual job timer, pause/resume, retained selection, native
GPU/CPU node details, refreshed detail, 40-column layout and authorized account
chooser. Node expansion added no query. The selected command entered/exited a
real PTY with its original terminal settings restored. No job or account setting
was changed. Source tests passed 1164 checks, builds/public scans passed and
Python 3.11/3.13 CI succeeded. Previous runtime and guarded rollback remain
available. This is bounded login-node verification, not fleet or human usability
acceptance.
