# Recorded work and native activity correlation

Status: implementation deployed on 2026-10-06 with native identity and
ordinary-user read checks; positive running managed-Run association still needs
a real sample. Existing read routes, scopes, capabilities and version identifiers
remain unchanged.

`run_link` is an optional nullable lowercase SHA-256 string on native `jobs/v1`
items and managed `compute.runs/v1`, `compute.run/v1`, `compute.my-runs/v1` items.
Missing or null means no usable correlation. A native row may also carry a
nullable `run_ref` parsed only from the existing canonical Run UUID marker;
it is an untrusted lookup selector and confers no access. Older consumers ignore this field.
No raw scheduler comment or credential is published. The Run reference is an
object selector already used by the managed APIs, not a secret.

The shared producer hashes a canonical JSON array containing the namespace
`compute.run-link/v1`, authenticated actor, site, cluster, native username,
frozen native account, numeric scheduler reference and existing Run correlation
reference, and the locked scheduler database index. Control-plane lists join the original account once within the SQL
page, verify its ownership, and use the accepted Run's existing fields. There
is no per-project or per-Run native probe, table, cache, grant or new service.

The site obtains its side from the already authorized native row and its exact
execution identity, as described below. It uses the
same complete tagged-record parser as Run placement: fixed Slurm/parser version,
clean source header, exact single job, typed native times and execution evidence.
Ordinary native jobs, arrays, heterogeneous jobs and incomplete correlation
records keep their normal job visibility with a null link. Nothing is inferred
from a job number, account prefix or accounting history.

Long-running work can lie beyond the current history page. The same my-runs
GET accepts `run_refs`, a comma-separated unique set of 1–100 canonical Run
UUIDs, with no cursor and a limit covering that set; an optional workspace key only narrows this exact lookup.
The same current actor/site/workspace SQL relation filters it before returning
names. Unreadable or absent references produce no row. No native response is
trusted to authorize a Run, and no unbounded history scan is used. The terminal
batches only missing visible native references, at most five calls for its
existing 500-job bound, preserving the ordinary history page and cursor.

A consumer groups rows only when there is one matching non-null key on each
side, the site/cluster and scheduler selector agree, and the native observation
is not stale. Native submit/start times must fall from the Run's accepted time
(floored to Slurm's seconds) through the native observation, and no later than
its recorded finish when present. The recorded title and authorized workspace
remain the navigation target; a current native state remains a distinct fact.
A Run's own native detail is read through the existing job path and checked
again against its freshly read metadata before displaying it.

The scheduler database index must already have been bound by the original
Run reconciler. Slurm 26.05.1 queue JSON does not provide that index. For the
already visible, tagged, non-resized native records only, the gateway performs
one bounded `sacct` lookup by their **SLUIDs**, users and accounts. It requests
only JobIDRaw, DBIndex, SLUID, OriginalSLUID, User, Account, Cluster and Submit.
The native job number, exact current SLUID, original SLUID, user, account,
cluster and UTC submit time must all agree; duplicate conflicting indexes and
incomplete rows remain unlinked. A number-only history query is forbidden.

The lookup occurs after secondary visibility, state/partition filtering and
the existing page limit, with at most 500 native records. It supplies only
identity, never job state or statistics. Source failure leaves the authorized
native state readable with null correlation; the gateway never falls back to
history for a failed queue read. Age includes this lookup's time. Resized jobs
without a directly observed DBIndex remain unlinked, since accounting may lag
a resize. Copied comments and reused job numbers cannot select a prior SLUID.
No new reconciliation writer, DB field, grant, cache or history API is added.

This key is correlation for browsing, not authorization or an execution-attempt
identifier. Requeues can retain the database index; restart/SLUID and hardware
checks retain their existing owners. Scheduler comments are mutable. Billing must retain the existing
accounting binding; placement/statistics retain their exact Run/native validators.
Every subsequent Run, file, cost and hardware read repeats its own authority.
A native job outside currently readable Run records never gains their contents.
An uncorrelated or unavailable native observation does not mean that a Run
finished, failed, has no files, or costs zero.

Deploy the matching Center and read-gateway producers before relying on grouped
work. The client keeps both readable sources visible when correlation is absent;
it does not invent a relationship or silently fall back to a broader query.
Local correlation tests do not establish production parser compatibility, real
job acceptance or the complete scientific workflow.
