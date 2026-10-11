# Site-Local Interactive Read Plane

The shared read capabilities below remain independent of presentation. Source
retires the broad terminal workbench under [terminal scope](terminal-scope.md).
`sai tui` provides focused native query interaction plus explicit authorized
business reads; its local views do not use this remote gateway. Earlier TUI deployment
records below retain their historical evidence boundary.

The 2026-10-09 product clarification includes local native queries within the
shared human/Agent CLI, integrated with existing SSH helpers and aliases.
Reuse one native implementation under the current Unix identity; local queue,
node and quota reads need no gateway hop or Portal OAuth credential. This
document describes the separately authorized remote read plane, still needed
by Web and remote Agent consumers. The local job command now has its own native
implementation; further helper integration remains planned. Neither is delivered
by this gateway. Portal management uses business APIs, not this read gateway.

The workbench replacement adds central actor-owned Run discovery while retaining
this site's native read paths. Native job rows optionally include a scoped
`run_link` and canonical Run reference parsed from the existing marker. The
original queue read and signed filter remain. Missing DBIndex is resolved only
by one exact current-SLUID batch after the visible-page filter; this is not a
history fallback or another authorization store. The matching Center/gateway rollout completed on 2026-10-06, with remaining
positive managed-running association acceptance recorded below. It does not route every refresh through a new
central aggregator or create client project fanout. The replacement UI was selected on 2026-10-06; bounded ordinary-user and
SSH/PTY result reading passed. Historical receipts below retain their own
versions and do not establish whole-product acceptance.

## Unified compute delivery gate

The canonical workspace selector first reached Center in `4f343e3f5`. The
complete personal, organization and project producer and compatible Pilot
consumer were then deployed from the selected Portal main `95101a01e2b5` and
Pilot `ef617c6e90e9`; the later Identity/account Center release kept this READ
chain. Signed grants, response DTOs and authorization ownership did not move.

On 2026-10-06 the existing ordinary-user login exercised the immutable
`af1410430059` CLI/TUI candidate against real APIs. The authorized directory
contained all three account kinds. Each kind's Current queue and Records and
results worked at 40, 60 and 100 columns. Organization and project queues were
nonempty; this user's personal queue and personal/organization Run lists were
empty, so they do not prove positive Run creation in those kinds. The selected
existing project result kept the same complete file after cost, statistics and
resource navigation. Its final cost was settled; statistics were unavailable.
One existing running job also returned detail and a single-node allocation.

A project queue initially failed because native `squeue --json` output exceeded
the site's existing 8 MiB capture limit. The site READ service now inherits
Slurm's `SLURM_JSON=compact`, preserving the same native query and output limit;
the account's 550-row native response fell below that limit. This is a native
format selection, not a client fallback or a second source of truth. Larger
queues may still exceed the limit and fail closed.

After candidate acceptance, the shared `/opt/sai/cli/current` selector was
atomically moved from `b99963b` to `af1410430059`. The selected runtime on the
login node repeated the ordinary-user file, settled-cost and three-kind TUI
checks successfully; the stable command entry resolved to that runtime. Both
934-file runtime inventories and the protected CLI configuration passed
readback; the previous shared release and exact rollback
script remain available. Temporary test files and remote sessions were closed.
No new task, model call, budget renewal, physical-terminal or browser journey, or
personal/organization Run creation was part of this acceptance.

## Three-kind reader prerequisite

On 2026-10-05, gateway source `6ab564984` and shared CLI/TUI `b99963b` were
deployed ahead of the paired personal/organization/project domain change. Only
the gateway's shared Run binding module and package manifest changed; the CLI
used its existing versioned shared publication. The execution gateway, trust
inputs, shared CLI configuration and dependency sets were preserved.

The installed gateway parser accepted all three matching scope kinds and
rejected a mismatch using synthetic facts under its actual service UID. An
ordinary user's existing Identity login read the same completed task, settled
cost and complete output before and after the CLI switch. Real-API headless TUI
checks at 40/60/100 columns preserved file selection across cost, statistics and
catalog views. Statistics remained unavailable. The exact authorized native
queue was empty; its normal capability read had a journal start/finish pair.

This establishes prerequisite compatibility and existing-task continuity, not
new personal/organization Runs, positive allocation/statistics, physical-terminal
or native-browser acceptance. The original Portal/Pilot owner retains the
domain, migration and native plugin release. Remote staging and operator sessions
are closed; the previous gateway package and shared CLI release remain available
for rollback. No live rollback was exercised in this slice.

## Shared Pilot reader delivery

The 2026-10-04 paired release installed Center reader source `5912ea49d` and
Pilot Python `1787ab7`. Managed project/history discovery and original output
text reuse the existing authorized Run owner; native SSH job discovery uses the
same `jobs/v1` gateway observations as this CLI. Read selection does not change
execution, payer, directory or budget. The native gateway and shared CLI required
no update. Pilot's DSH, sandbox and interface artifacts remain at `b2a8b79`.

Production checks covered the actual service identity reading current projects
and native conversation metadata, plus an ordinary user's existing Identity
login reading the same completed task, settled cost and complete text output.
The Python switch preserved history, budgets and Session records. Operator
sessions and temporary staging are closed; rollback artifacts remain private.
This is shared reader delivery, not native browser discovery or full workflow
acceptance. The separate three-kind compute billing contract remains with its
existing owner; this release does not broaden managed historical scope.

Status: the basic job list/detail/allocation runtime and HTTPS routes were
deployed on 2026-10-01. Normal user authorization, self/account lists and matched
production issuance/read-use audit pairs passed. Later ordinary-user acceptance
also covered positive job detail/allocation in a non-default organization and
isolated client network failure followed by recovery with the same capability.
The complete task journey remains open. Native Lustre quota has local transport/gateway code
but is not enabled by this release. Billing and resources retain their own gates.

The deployed unified job-observation implementation below changes the estimate reader and
Portal presentation and has been paired into production. The later TUI
selected-job Cost action reuses central same-observation detail pricing;
its paired CLI route and consumer were installed on 2026-10-02. It adds no
gateway operation, native reader or Pilot operation. The live historical-task
check and still-empty current-job scope have separate acceptance boundaries.

## Purpose and ownership

Frequent queue/detail refreshes should not perform central policy resolution on
every request. Portal makes the relatively rare authorization decision and the
site gateway reads local native facts under a short-lived capability.

Dynamic facts default to on-demand native reads at the site. The gateway
normalizes those reads; it is not a replicated scheduler or storage database.
The terminal's common compute workspace is resolved by Portal's existing job
READ owner before issuance. It does not enter the signed grant or gateway query:
the gateway continues to verify the same exact native user/account constraints.
This request extension needs a paired Center/client release, not a new gateway
operation, account mapping cache or authorization service.
Coalesce concurrent identical reads and use brief, explicitly timestamped
reuse where the source cost warrants it. A new UI does not require a central
telemetry store or an always-running full-inventory collector.

Slurm queue/detail adapters already provide this native-read foundation. A
future resource-state operation must extend the reviewed
operation contract and reuse the native source/parser, without importing the
write-capable storage adapter's administrative authority. A native quota query
is distinct from a recursive directory scan; the latter does not belong in
the synchronous interactive path.

The separate `storage quota-summary` command reads existing Portal observations
and delivery state. It is a central business read, explicitly labeled by source
and observation time; it does not enable a native storage operation in this
gateway or replace the on-demand design.

ComputeRun intents, idempotency, execution receipts, membership and settlement
remain durable control-plane facts. Current native observations do not replace
those records, and a client refresh cannot advance their state. Historical
sampling is added only for a named feature with a bounded retention policy.

| Component | Owns | Must not own |
| --- | --- | --- |
| Shared contract | capability grant, request, normalized DTO, freshness, bounded error | ORM or native commands |
| Portal issuer | identity/membership/site policy, scope resolution, signing, epoch, audit of issuance | interactive Slurm reads |
| Site-read gateway | signature verification, filter narrowing, native reads, short cache, audit buffer | membership/RBAC, wallet/ledger, provisioning, scheduler writes |
| Native adapter | bounded `squeue` and `scontrol show job` reads | user authorization |
| Remote `sai-cli`/`sai-pilot` consumer | explicit intent, capability renewal, transport, allowlist validation, rendering | signing keys, policy or pricing arithmetic |
| Planned local CLI provider | integrate existing native helpers with human/JSON presentation under the current UID | Portal authority, elevated privileges or a new scheduler |

The gateway is a separate low-privilege runtime role. It is not the existing
write-capable site-agent process, and it is not packaged in the CLI wheel.

The independent `jobs.placement` operation reuses one native allocation read,
then joins only its nodes to a protected, signed operator inventory. Portal's
site opt-in is false by default and preserves the existing job-reader policy.
The publication head pins an exact bundle digest/generation; the gateway checks
signature, current publication, site/cluster and expiry before returning.
It does not collect room topology, poll hardware, publish inventory or expose
unrelated nodes. Withdrawal or source failure never reuses a previous mapping.
The result labels location as operator-recorded, with verification and expiry
times. This implements the first asset association, not physical-incarnation
proof, utilization or deployment. Consumers share
[`jobs.placement/v1`](../contracts/job-placement/v1/README.md).

## Capability

Managed-task project and storage-scope discovery stay at Portal. Each reuses
its own current membership and site read policy, returns a bounded name/selector
page and neither queries the native site nor issues another capability. Exact
selection narrows that same directory to one readable key. Storage discovery
does not depend on task admission or promise native quota availability.

Run-bound node registration reuses this gateway and its normal allocation and
signed inventory readers. A strict `interactive-run-read-grant.v1` narrows
`jobs.placement` to a server-derived actor-owned Run, username/account
intersection and submission correlation. Ordinary `interactive-read-grant.v1`
is unchanged. Native fixed-version identity is checked before projection, then
execution/allocation are read again before inventory confirmation and final
capability verification. Response `compute.run-placement/v1` contains the Run
and execution evidence plus the unchanged placement DTO. Old or unbound readers
fail rather than downgrade. No helper, secret, scheduler-state store or node
RPC is added; physical GPU binding remains a separate evidence requirement.

Managed-run logs and declared output-file listings retain their existing
ComputeRun readback path through Portal and its dedicated `interactive-read`
site credential. The CLI holds only its Identity token and sends no file path,
username or site secret. Portal checks current file READ and frozen mount
lineage before calling the two bounded site methods. Those methods reject
redirects and responses above 1 MiB; the log content itself is at most 64 KiB
and an output page at most 100 files. This does not create a file capability in
the native jobs/quota gateway or a second filesystem reader.

Native task statistics have a different Slurm identity boundary. A bounded
26.05.1 preflight found `sstat` denied for the existing site-read service UID,
with exit status zero despite node-level errors. Reading another running job
as its actual owner succeeded. No gateway permission or service was changed.
The implemented statistics read therefore uses the existing managed-Run
interactive-read route and permanent UID-dropping `sai-site-run` helper, with an explicit
read-only operation. It is not a gateway retry or privilege fallback. Scope,
native job owner/account/correlation and before/after execution/allocation
evidence must agree. Unknown metric values remain unknown. The client never
executes `sstat` itself. `runs stats` and the Web/Pilot readers share
`compute.run-stats/v1`; no collector is introduced. The paired site role is installed; an ordinary user exercised the complete
CLI/Portal/native read and received an explicit unavailable observation for a
historical task. Positive running metrics and other-client acceptance remain open.
See [the digital-twin design](digital-twin-design.md) for fixed-version semantics.

The outer token is exactly the `sai-authz` v1 envelope. Product fields are the
typed `interactive-read-grant.v1` payload:

```json
{
  "version": 1,
  "iss": "sai-portal",
  "aud": "sai-site-read",
  "surface": "site-read",
  "site": "site-a",
  "operations": ["jobs.list"],
  "policy_epoch": 7,
  "jti": "opaque-id",
  "nbf": 1785427000,
  "exp": 1785427180,
  "grant": {
    "schema_version": "interactive-read-grant.v1",
    "actor_ref": "opaque-user",
    "cluster_id": "cluster-a",
    "scope_type": "project_account",
    "subject": {"slurm_user": null, "slurm_account": "project-example"},
    "partition": "gpu-standard",
    "states": ["PD", "R"],
    "job_id": null,
    "limit": 100
  }
}
```

Portal derives the exact compound subject through the existing resolver with
`entrypoint=cli` and active shell access. Site-read operations are exact and
independent: `jobs.list`, `jobs.detail`, `jobs.allocation`, and `billing.running-estimate`.
No job operation grants billing. Allocation uses the same exact job grant
constraints as detail. The gateway verifies issuer, audience,
surface, site, operation, key/epoch, time window, JTI revocation, grant shape,
and request subset before invoking the adapter.

The CLI sends the capability only in `X-SAI-Capability`. It never receives a
signing key, accepts a capability from argv/environment/config, or sends the
Portal Bearer to the gateway.

The client opts in using a trusted TOML `site_read_base_url` origin. Job
list/detail, allocation and explicit native quota use it; catalog, stored quota
summary, authentication and running cost remain central.
The read origin participates in the capability cache key. No failed gateway
read falls back to another source.

## Request and response

The gateway request is a `GET` with no authorization query parameters; the
capability carries the authority. Portal and CLI retain
`billing.running-estimate/v1`; the implementation replaces unused gateway pricing
with native observations for Center to price. Direct jobs use the
explicit gateway `jobs/v1` envelope documented in
[portal-api-contract.md](portal-api-contract.md#direct-site-job-reads), while the
default Portal job envelope remains unchanged. Direct jobs include site/cluster,
resolved subject, source freshness, truncation and an ETag; no Portal membership
role is inferred. Unknown additive fields may be
ignored only after recursive allowlist validation. Paths, scripts,
environments, raw scheduler data, wallet, ledger, and provider diagnostics are
never returned.

The reusable site runtime adapter supports these bounded native reads:

- `squeue --json`, with optional user/account/partition/state narrowing and a
  bounded result limit;
- `scontrol show job <ids> --json`, for detail and allocation snapshots;
- `scontrol show hostnames <expression>`, only to expand an observed allocation's
  host expression. This does not query all-node state or physical inventory.

The paired `jobs.allocation/v2` projection also reads `gres_detail` from that
same job response. Slurm JSON already enables detail. Index-to-node binding
uses the native ordered expansion before sorting; it adds no node-state query.
Unknown GRES remains null independently of valid CPU/memory observations.

It has no `sacct`, enforcement, reservation, metadata, provisioning, quota, or
write method. Commands run without sudo, with explicit timeout and output
bounds. A source failure returns a bounded unavailable result; it never falls
back to broad accounting or a guessed empty success.

## Native Lustre quota

The independent `storage.quota.read` operation uses `storage-read-grant.v1`;
it does not add storage subjects to the Slurm grant. Portal binds each current
typed project-ID assignment to its filesystem namespace and mount, using the
existing workspace/site and directory visibility policy. The gateway shares
the original signature, epoch, revocation and expiry verifier.

Its protected mount mapping supplies a readable quota anchor and exact expected
native filesystem source. The gateway checks `findmnt`, then executes only
`lfs quota -p` for authorized subjects. It has no sudo or write adapter. Its
pure parser is shared with the existing storage readback implementation, without
shipping storage administration code in the gateway package.

The [native quota DTO](../contracts/storage-native-quota/v1/README.md) separates
subject observations from business pool totals and stored delivery state. A
failed, partial or inaccurate native query returns an error, never old data.
Commands have a deadline and a captured-output limit; the runner still has no
streaming memory ceiling.

On 2026-10-07, the installed reader ran under the actual service UID against
Lustre 2.17.54 in a temporary systemd namespace. The native adapter validated a
read-only mountpoint and read one existing project quota with no Linux
capabilities, while the original home/organization paths remained inaccessible.
The temporary unit and anchor were removed; the formal reader and executor
processes stayed unchanged. This used an operator-created synthetic grant and
does not establish user capability issuance or an enabled production route.

The exact HTTPS quota GET route was subsequently published from Portal source
`86b18b4e9`, retaining verified upstream TLS and capability-only forwarding.
Unauthenticated GET returns `401/site_read_capability_required`, POST returns
405, and undeclared subpaths stay 404. Other ingress configuration and static
release digests were unchanged. This is a routing check, not a quota data read.

The formal service was then configured with two control-plane mount references
sharing one native filesystem and one read-only quota anchor. A bounded read-only
control-plane lookup supplied the references; source verification used the actual
service namespace. The mapping, one environment path and a systemd read-only bind
were installed, and only the reader restarted. Its runtime, trust inputs,
enablement and independent executor were preserved. The native reader passed in
the formal namespace under its unprivileged UID; an ordinary user's basic job
read succeeded before and after the restart. Temporary probes were removed and
operator sessions closed. Protected configuration backups and rollback remain.
These native probes still used operator-created grants, not user authorization.

An ordinary user's browser-approved isolated device session then read one
authorized Home quota through the installed CLI, real Portal issuer, public
HTTPS gateway and native Lustre reader. Center issuance and journal start/finish
records matched the actor, capability digest, workspace and quota subjects.
The temporary refresh revocation was acknowledged and the isolated profile was
removed. The original login still read jobs and still rejected storage without
its own scope. All operator staging and sessions were closed.

This proves one personal-scope remote read and its local journal evidence,
not all workspace cohorts, load behavior or Web/Agent integration. Managed
configuration still requests compute/billing only; the isolated test did not
enable storage for existing sessions. Device caches are scope-bound. A future
permission expansion must preserve basic sessions and obtain explicit consent.

## Native observations and running estimates

The implementation adds `native_usage` to each gateway job row, using
`slurm.job-usage/v1`: typed native allocation and database identity from that
same observation, with no amount, payer or price revision. Portal can attach
an independently authorized estimate to the same row; clients do not join
two lists by Job ID. Existing CLI job allowlists ignore the additive field.
The [API contract](portal-api-contract.md#native-usage-and-optional-estimates)
defines the exact fields and optional Portal request.

The separate `billing.running-estimate` operation keeps its existing grant
shape. `GET /v1/site-read/billing/observations` returns the complete authorized
`billing.job-observations/v1` snapshot to Center, bounded by 200,000 rows and
16 MiB. Exceeding either bound or an incomplete source causes failure, not a partial total.
Its existing queue reader retains `SETTLING`/`TERMINAL_GAP` observation gaps;
these are not native completion or billing settlement facts. Ordinary job pages
remain on demand and do not acquire a full queue merely to display an estimate.

Portal remains the only price owner and returns `billing.running-estimate/v1`
to existing cost consumers. Missing price or native facts produce null amounts
and uncertainty. Amount availability never redefines scheduler state. The unused
site gross-only v2 and signed price-bundle path are removed by this implementation.

Interactive reads do not create exposure, allowance, wallet, ledger, or payment
rows. Existing billing workers independently validate observation identity,
coverage and final accounting facts. UI refresh cadence does not drive that path.

## Cache and audit

Native source snapshots may be cached briefly. Outward DTO/cache keys include
actor digest, site, surface, operation, scope, normalized filters, policy epoch,
resource/pricing revision, capability digest/JTI, and visibility policy. A key
containing only site or query is invalid. Expired capabilities cannot trigger a
native read; stale local data is display-only and explicitly marked.

The implemented default job path reads on demand with native subject/filter
arguments and then filters again before limiting. It does not reuse the
billing collector's cluster-wide cache or synthesize terminal states. Short
reuse/coalescing is a future measured optimization, not a new required service.
The ETag describes only authorized normalized output and truncation; unrelated
job changes cannot alter it.

The gateway emits structured read-use events through its existing systemd
journal stream. A single bounded queue reserves start and finish slots after
capability/filter validation and before native/cache reads. Each request gets
an independent read reference even when client request IDs repeat. A Run's
before/after observations share that reference. Queue saturation or a known
writer failure rejects reads; shutdown waits at most two seconds on the writer.
Records include actor, site, scope, normalized filters, operation, JTI digest,
count, source freshness, outcome and optional request ID. Tokens, native errors,
paths, scripts, environment and response bodies are excluded.

The queue is in memory and writes asynchronously. Stream write/flush is not
confirmation of journal persistence or remote delivery; a crash may leave a
start without a finish. Such a record means outcome unknown. The central
capability-issuance audit remains the durable authorization record. Journal
retention and collection stay with the existing site logging owner, with no
new spool, exporter or read-replay service. Production acceptance must verify
the actual service UID, journal collection and failure behavior, separately
from local HTTP tests.

## Explicit site selection and ingress topology

Decision (2026-10-01): users explicitly choose the site. A saved selection may
be reused and remains visible; latency, capacity or failure must not silently
move a request or task to another site. Address routing serves the selected
site, not a new scheduling decision. This is the target deployment model;
the multi-site and direct-browser paths below are not yet delivered.

Each site has a stable logical HTTPS origin, independent of its public IP:

| Selected site | Logical origin | Deployment |
| --- | --- | --- |
| Site A | `https://site-a.api.example.org` | Its own ingress |
| Site B | `https://site-b.api.example.org` | Shared ingress with C |
| Site C | `https://site-c.api.example.org` | Shared ingress with B |

Independent ingress is the one-site case of shared ingress. Hostnames B and C
may resolve to the same IP; fixed virtual-host mappings forward each to its
own gateway. Unknown hosts fail closed. Gateway authorization still verifies
the signed site/cluster/operation/subject; DNS and Host are not permission.
An ingress can run beside the gateway and need not imply another machine.
Outbound NAT alone is not HTTPS ingress: a private site can use an existing
private network/VPN to a shared ingress that accepts inbound HTTPS.

Reuse two mappings in existing protected configuration: site ID to client read
origin, and ingress hostname to gateway upstream. No new discovery service is
required. A future authorized site directory may publish the first mapping,
but accepting it requires a coordinated client contract; arbitrary user URLs
and response redirects cannot choose credential destinations.

The implemented `sai sites` directory is narrower: it reads published names
and IDs from Portal before explicit selection. It exposes no network origins,
adds no gateway request and makes no claim about the caller's site permissions.
The future routing-directory contract above remains separate.

Site-local TUI/Agent reads should use the local route. Prefer site-local DNS
for the same stable hostname where available; otherwise select a protected
site-local origin explicitly. Preserve certificate name/CA validation on every
path, including ingress-to-gateway TLS. A browser-facing origin needs a
certificate its clients trust. Do not discover routes by probing, downgrade
TLS, or fail over to a different site. Any later alternate ingress must serve
the same site under a separately reviewed failover policy.

Identity login, Portal capability issuance/renewal, membership, task records
and final billing remain central. Authorized native reads use the selected
site path during the capability's remaining lifetime. Center loss prevents
renewal; expiry fails closed. The current issuer's default 120-second lease
is not an unlimited offline grant or an immediate revocation guarantee.
Routing changes do not grant file, Pilot execution or administrative access.

WebUI and Agent should share these site semantics and DTOs, not necessarily
one network origin. Direct cross-origin browser reads require an explicit
console-origin allowlist, bounded OPTIONS/preflight support for the capability
header, and no browser credential mode, Identity Bearer or login cookies at
the site gateway. Shared proxies must not cache private responses or log
capabilities. Web job/allocation reads currently use Portal's authorized relay;
retain it until the direct-browser replacement is reviewed. Pilot's existing
Session-bound capability issuance is a separate consumer path, not evidence
that every Pilot read uses the Web relay or that multi-site routing is complete.

Current code has one protected CLI read origin per profile, a server-side
gateway URL per Portal site, and a single-upstream basic ingress renderer.
Unmanaged `--site` changes only the site selector, not the profile/read origin;
managed wrappers fix the operator-selected default profile and reject site,
cluster and profile overrides. Explicit managed multi-site selection therefore
needs a reviewed site-to-origin binding, not simply removal of wrapper checks.
Capability caches already bind site/cluster/request and read origin; Identity
credentials remain bound to their central issuer/resource, not each site.
There is no client endpoint discovery, multi-site ingress rendering or
direct-browser CORS contract; current ingress rejects OPTIONS. The deployed
center ingress is the first site's connection, not a required global hub.
CDN, automatic region selection, service mesh and a replicated facts database
are not prerequisites.

Delivery order stays basic reads, real-user authorization/audit acceptance,
then the complete task journey. Before adding another site, validate its
explicit site/origin binding, local and public paths, wrong-site rejection,
single-site failure isolation and lease expiry during center loss. Measure
actual routes/latency and native command load; local collection alone does not
prove that client traffic avoids the center. DNS or ingress migration must
preserve site identity and have its own rollback. This decision starts no
production topology change and does not delay the existing basic-read gate.

## Network and rollout boundary

The unified observation implementation requires no site price configuration.
Authorization keys, epoch and revocations remain required startup inputs;
inventory and native storage mappings retain their own opt-in. Its native
billing route, matching Center reader and role packages require a paired release;
the already deployed basic jobs routes do not prove that release complete.

Managed Run step statistics use the existing owner-UID site-run path described
in [the digital twin design](digital-twin-design.md), independently of this
capability gateway. The low-privilege gateway cannot assume `sstat` permission.
Portal obtains current actor-owned Run READ, derives exact native selectors and
uses the existing dedicated interactive-read credential. The fixed helper drops
privileges before reading; it adds no gateway sudo rule, collector or cache.
Its total native budget is 15 seconds, 4 MiB stdout/stderr and 16 commands; the
HTTP receipt is bounded to 1 MiB. Oversize or incomplete observations fail closed.
Client JSON and three UI views share `compute.run-stats/v1`. The 2026-10-02 site role installation and ordinary-user no-sample read
are recorded below; a positive active-step sample is still required.

A transport proxy may be used for center/satellite topology; it only forwards
the request and response. It does not authorize, read Slurm, calculate money, or
hold a shared site-agent secret. Both center and satellite use the same gateway
package and contracts; only protected deployment configuration selects the
origin.

The delivery order is: shared vectors and verifier; independent gateway role
and systemd unit; native observation/Center pricing contracts; CLI/Pilot compatibility;
development-stack smoke; then an approved GET-only live canary. Local tests and
package builds do not prove a live site or production service.

## Isolated native HTTP acceptance

On 2026-10-01, candidate gateway source
`9401a32bc8887d82062797f5e0aa583592044c23` ran over loopback HTTP under the
existing low-privilege service identity against real Slurm 26.05.1. A bounded
self list and before/after allocation of one existing running job succeeded;
its two-node allocation and execution observations remained unchanged. The list
first item was a different job, so this is not a list-to-selection journey claim.
Three rejected requests and three authorized reads produced exactly three audit
pairs. The temporary worker, descendants and listener ended before cleanup.

This used temporary signing inputs and isolated dependencies, without modifying
the installed service, its environment or any workload. Audit output went to a
private file, not the production journal pipeline. The formal gateway remained
inactive; its environment, independent Python runtime and verification inputs
were not configured. This establishes native candidate HTTP behavior, separately
from Portal/Identity authorization, production activation, signed asset
publication, physical GPU identity, utilization and native Lustre acceptance.

## Basic production connection

The 2026-10-01 basic release installed the independent runtime and read-role
`36adeec1d19b79404a9d53385183adb68b7b57b0`, activated its TLS listener with a
separate site certificate configured for automatic renewal, and connected the
existing public HTTPS origin through three explicit GET routes. Center kept its existing
code and signer; only its gateway URL/timeout projection changed. Shared CLI
`cca92ae4b3f308ead4d6514cf645757482acfc34` is published once on NFS with the
protected read origin. No per-compute-node install or new proxy service was added.

The public job-list probe returned 401 without a capability and 405 for HEAD/POST;
placement and native-quota probes returned 404. Positive detail/allocation checks
remain candidate evidence, without a real-user production example. Routing and
shared-CLI rollback and restoration were exercised; other processes and static releases
remained unchanged. The first device authorization expired; a later ordinary
user-approved device flow succeeded. Subsequent acceptance reused that user's
protected cache after the paired Identity/Center release, without a new login,
borrowed credential or administrator-issued user token.

Self and one authorized organization list returned 200 with native `squeue`
freshness; both were empty and matched separately bounded native reads. An
unauthorized account request was rejected. Current production journal contains
start/finish pairs for both successful reads. A bounded, read-only Center audit
query matched their capability ID hashes, actor, scope, subject, operation and
limit. Signing and reading use different HTTP requests; matching request IDs
is not required, and the ingress generates its own read request ID.

A separate bounded probe held one normally issued capability through natural
expiry: its native read first returned 200, the same expired capability was
rejected with 401, and normal acquisition then restored 200. It used the
installed client libraries without automatic renewal for the expiry request.
No token was printed, exported or used to modify the server's revocation state.

The 2026-10-02 TUI follow-up installed Center `792950722ff4` and shared CLI
`f08834e7bd91`. Only the Center CLI route and package manifest changed; existing
configuration, gateway `311d5c73ceaf` and Portal static content were preserved.
The client was published once on the existing NFS path. Real-user historical
Run details, logs, three output records and settled cost passed, followed by
a headless workbench journey using those same production reads. Its Web link
preserved the selected output; browser/Pilot opening was not exercised.
The live queue was empty, so this does not close positive current-job costs.
All operator sessions and staging were closed; previous packages, selected
releases and rollback evidence remain outside this repository.

This proves normal authorization, native list reads and local journal/issuance
correlation. Empty lists do not prove job detail, allocation or a task journey.
The earlier expiry probe changed no workload, account binding or authorization
state. The explicit single-capability revocation check below is a separate operation;
membership-policy revocation, journal collection/failure handling and full gateway
package/runtime recovery remain separate acceptance work.

## Unified observation release

The unified job/estimate release is deployed. Portal's job page uses one native
observation and central optional pricing; the ledger no longer has a second
running-job list. The financial snapshot collects only its authorized native
user/account scope, with bounded scope-isolated retention. The old site price
engine and interactive site-agent query path are removed.

Production self/account lists and non-final estimates succeeded through the
normal user credential cache, with matching gateway journal pairs. Those scopes
were empty, so they do not prove positive detail/allocation or the full task
journey. Source truncation, pricing unknowns and financial permission retain
separate states. The public static artifact matched the deployed package; no
Identity, Pilot runtime, business schema or settings were changed by this slice.

## Native task-statistics role delivery

On 2026-10-02, the existing site execution-gateway role was updated from its exact
installed baseline with the already implemented statistics reader. Release source
`6e0d1e2d193d05a4880ad089dc0611d66a874871` changes three existing runtime files
and adds two modules; the role's other payload, dependency, environment, sudo and
unit boundaries remain. Its package and 70 local native/helper/API/artifact checks
passed. Only this execution service restarted; the independent capability reader
and its configuration stayed unchanged.

An ordinary user's existing approved credential read a historical Run through
CLI, Portal, the dedicated site API and the owner-UID native path. The response was
`unavailable`, with the actual read window, null execution and no steps; it did
not fabricate zero metrics. Existing output and authorized job-list reads still
succeeded. Uploaded staging and operator sessions are closed; the previous role
package and audit are retained for rollback. No computation or billing action,
new authorization, asset publication, GPU mapping or 3D scene was created.

This proves installed code and a real authorized no-sample path. Positive running
CPU/RSS, full browser/Agent consumption, physical assets and permanent execution
identity remain separate acceptance gates. No source fallback was introduced.

## Single-capability revocation acceptance

On 2026-10-02, an ordinary user's existing approved session obtained one
`self` / `jobs.list` capability limited to one row. The real gateway accepted it.
Only that test JTI was added to the protected revocation bundle. The current
verifier loads this bundle at startup, so the existing read service was explicitly
restarted; changing the file alone was not presented as immediate revocation.

The same capability was rejected with 401 before its expiry. Normal client
acquisition/read then returned 200. After the test lease expired, the exact original
bundle bytes, ownership and permissions were restored and the service restarted;
a final normal read returned 200. The execution gateway stayed unchanged. This
required two intentional read-service restarts and does not prove zero downtime.

The standard protected CLI credential/capability cache was reused without export.
No full token entered command arguments, probe files or logs. Only non-authorizing
JTI/expiry metadata was handed to the operator. A matching accepted-read start/finish
pair remained in the local journal. All temporary probes/directories and operator
sessions were removed/closed; normal user caches and protected audit were retained.
No account, membership, signing key or policy epoch was changed.

This proves revocation of that one lease, not immediate membership withdrawal,
a cached-capability 401/retry path, external audit delivery or full package recovery.
The observed normal-client recovery was a fresh successful read.

On 2026-10-05, a separate check exercised the installed client's actual cached
401/retry path. An ordinary user's existing device session acquired a narrow
self-list capability in an isolated access/capability cache. After revoking only
that test JTI and restarting the reader, the same cached token returned 401 about
52 seconds before expiry. The client then made exactly one successful capability
issuance and retried with a different token; the gateway returned 200 about
0.42 seconds after the refusal. Token digests, cache source and response times
were checked without exporting credentials.

After expiry, the original revocation bytes and complete ACL, including the
execution reader's named access, were restored and the reader restarted again.
A final ordinary read returned 200. The original refresh store was used normally
and was not rolled back; only the test access cache and staging were removed.
Both intentional reader restarts completed with no unexpected restarts, and the
execution gateway remained unchanged. Observed access JWT lifetime was 300
seconds, capability lifetime 120 seconds and gateway leeway zero; these values
alone do not prove the complete Identity-session revocation window. Membership,
shell-policy and Identity-session withdrawal remain separate acceptance gates.

## Managed artifact text boundary

The first direct task-output text reader extends the existing managed log/file
chain: current Center Run/file authority, dedicated site interactive-read credential,
and the native owner-UID helper. It is not a new operation on the capability job
gateway and is not direct storage access by a CLI. Its paired content contract
bounds a section to 64 KiB, forbids client paths and stops at file-version changes.
Future site-direct content routing must preserve this same authority and file scope;
this source change does not claim that transport migration or deployment is done.

Complete output downloads use a separate narrow `compute.run-artifact-download/v1`
grant issued after the same current Run/file checks. The CLI receives an exact
site-files URL and version-bound capability, then reads binary byte ranges
directly; Identity Bearer remains at Portal. The client does not choose native
paths or users, reuse the jobs capability, or fall back to filesystem access.
8 MiB ranges, version-preserving renewal and atomic local publication are source
implementation; paired server/site deployment and real transfers remain separate
acceptance. This adds no persistent transfer state to the CLI.

## Native active-runtime correction

The 2026-10-03 paired release deployed the shared normalization fix from
`99f32e5551d30a93825c70f3cf0438a10c1e440f` onto each role's actual installed
baseline. It preserves Slurm suspension counters and freezes the last observed
duration for retained queue rows. No client, pricing engine, authorization,
schema or UI was added; the existing risk reader also consumes the corrected
duration. Final billing remains independently validated.

The real read-service identity checked two existing running jobs before and
after installation against Slurm's own RunTime, with matching seconds. Ordinary
user reads through the stable CLI still returned the empty queue/estimate and an
existing task's settled cost and complete text. Controlled inputs and original
service/timer states were preserved, and temporary staging/sessions were removed.
There was no live suspended-job sample, new computation, model request or browser
journey acceptance. This data correction does not establish completion of the
Pilot-native compute plugin or the estimate-to-final workflow.

## Replacement workbench delivery

On 2026-10-06 the shared CLI selected source `f62956ff6921`, paired with Center
`64806718031b` and dedicated read gateway `12001fdd79fb`. Each role used a full
merged main source and its original packaging, with prior software retained for
rollback. Private configuration, verifier inputs, dependency runtime selections,
service enablement and the independent site executor remained unchanged.

The native preflight found no DBIndex in queue JSON. The source correction uses
one exact current-SLUID identity batch after the authorized visible-page filter,
not a broad accounting read. Two real native samples validated that adapter as
the service UID. There was no tagged running managed sample, so the test did not
establish a positive live Job/Run association.

An existing ordinary user's selected runtime read recorded work, the same text
result and final cost, restored file position, and discovered all three account
kinds at 40/60/100 columns. Organization/project native lists were nonempty;
selected detail and allocation reads passed. Actual SSH/PTY Enter navigation
read that output and exited successfully. Public console and independent Pilot
entry responded normally. No new job, model call, user credential or browser
Session was created. User comprehension, native Pilot resource/result continuity
and the complete scientific workflow remain open.

### Organization scope compatibility

Remote organization reads include Portal-authorized project subjects, each with
its own user restriction. The versioned grant and DTO changes are described in
[the shared API contract](portal-api-contract.md#organization-job-scope). Native
`sqa` remains a separate Unix-authorized read; its hierarchy is not business
authorization. Deploy gateway and CLI/Pilot readers before the Center issuer;
exact Run, self, personal and project contracts remain unchanged.
