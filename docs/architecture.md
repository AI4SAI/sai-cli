# sai-cli Architecture

Status: native/API queries and the first Portal management action are implemented;
broader management remains planned.

## Purpose

`sai-cli` translates human or Agent intent into a native local query or an
authorized SAI API operation, then renders a human answer or structured result.
It runs on cluster nodes, user devices and dedicated isolated SAI user VMs.
The current implementation provides HTTP reads, explicit local job/resource/quota
queries, and a default-account management operation. Broader Portal management
remains a target. It owns neither
business authorization nor scheduler decisions.

The [product task map](product-delivery.md) connects these boundaries to complete
human and Agent journeys. The public client, contracts and bundled Agent guidance
use Apache-2.0 with separately identified upstream licenses; each release retains
its artifact and approval gates. API coverage and interface symmetry are not
substitutes for a useful completed task.

Terminal queries integrate familiar Slurm/Linux helpers and SSH aliases;
account, access, budget and cost facts come from their existing business owners.
[Command scope](terminal-scope.md) retires the broad workbench without removing
local query convenience or authorized Agent management from the product.
The current no-subcommand entry selects the existing account summary handler; terminal detection
changes only plain-text versus JSON presentation, not the data source or authority.

The architecture keeps the following responsibilities separate:

| Owner | Responsibility | Explicitly does not own |
| --- | --- | --- |
| `sai-identity` | Account identity, credentials, MFA, sessions, consent, OIDC/OAuth subjects, and shared profile | Portal workspace/membership/site/billing policy or scheduler facts |
| Portal control plane | Workspace/membership, site access, compute-account ownership, policy version, authorization, and final billing facts | Identity credentials and high-frequency scheduler reads at every remote site |
| Site-local read plane | Verify a narrow capability, further restrict filters, read native site facts, cache briefly, and buffer audit records | Membership or billing policy decisions |
| Local native query adapter | Reuse shared helpers and native Slurm/Linux/Lustre under the caller's Unix identity; normalize an observation once | Portal membership, pricing, privilege escalation or a second scheduler |
| `sai-cli` | Common operation semantics, user authorization for remote operations, local/API routing, validated inputs/results and human/JSON presentation | Business databases, independent policy, pricing arithmetic or Agent orchestration |

## Local queries and portable Agent management

Portable `configure URL` uses the explicitly selected service's public auth
configuration and standard OIDC discovery. Portal projects its existing resource
verifier settings; the client creates its ordinary user profile without replacing
an existing one. This adds no credential or service directory. A fresh profile
requests only the installed site-discovery permission; later task permissions
use normal explicit consent. See [the connection contract](../contracts/cli-connection/v1/README.md).

```text
human aliases / commands ----+
user-controlled agent ------+--> common CLI operation
                                | local native observation
                                +--> existing native helpers / Slurm / Lustre
                                | business query or management
                                +--> Portal domain API --> existing writer/task
                                | remote native observation
                                +--> selected site's authorized read gateway
```

Local queries execute as the current user using native clients. They do not
bootstrap through Portal, load financial context first, or require a central
token. The shared native helpers are the integration starting point. `sai jobs
local` and the packaged `stat_job`/`stat_job_all` wrappers now share one Slurm JSON
reader and the existing job presenter. Resource helpers now have a common
`resources local` implementation over one per-node `sinfo` response; their shared
migration has passed bounded ordinary-user checks documented in
[terminal scope](terminal-scope.md#local-resource-delivery). Extract/reuse a single implementation
where machine-readable output needs it; do not parse a rendered table, launch
an interactive login shell or install a daemon for every query.

The helper's human presentation retains its prior visual contract. Native
resource tables have a dedicated renderer over the same observation; terminal
color and column layout never change collected facts or machine JSON. Shared
GPU/CPU entrypoints request the node detail view by default.

Execution source is selected before the request from operation intent, explicit
site selection and installed configuration. A local read may expose different
native visibility from a Portal-scoped read; report that scope instead of
equating the two. A remote denial cannot silently fall back to a local read.
Native cluster visibility grants no Portal management, file or financial right.

Personal devices and user VMs use the same CLI and user/delegated Identity flow.
An isolated VM does not imply Slurm credentials, a filesystem mount or extra
rights. Agent operation discovery, JSON and noninteractive invocation do not
require Pilot Session/Pool activation. Existing CLI shell-enabled read policy
is a current API constraint, not the general authorization policy for all future
Portal management. Pair the proper user/delegated API boundary with each domain
service; do not remove shell checks from current contracts to emulate support.

`sai describe` derives its offline command catalogue and argument syntax from
this same argparse registration. Source/effect/scope metadata is attached there,
not in a second dispatcher. It never inspects credentials or probes availability;
current authorization remains with the called operation. The installed base
package can describe itself without native tools or optional UI dependencies.

The same base wheel contains its official Agent guidance, exported offline by
`sai skill`. Guidance routes tasks to the installed `describe` metadata; command
syntax and permission prerequisites retain their existing parser owner. Agent
hosts can consume the skill without adding a CLI-owned orchestration runtime.

For writes, Portal remains the single domain writer. Reuse supported action
validation, idempotency/concurrency checks, approval rules and durable site tasks.
Return their existing identifiers and accepted/executed/failed outcomes; allow
the caller to inspect completion without creating a second workflow engine.
An available browser route is not automatically an OAuth Agent endpoint.
Local source availability and remote management do not depend on 3D deployment.

`sai sites` projects the existing published Portal site chooser to a bounded
ID/name page. It provides the missing discovery step before explicit site
selection on a portable client. Discovery does not resolve credential origins,
select a site, or grant site access; each later operation keeps its own policy.

The first write uses Portal's existing preference writer and projection tasks,
behind an explicit Identity resource adapter. An expected saved account prevents
overwriting a concurrent choice; the existing idempotency record preserves the
original acceptance on replay. The CLI never retries this PUT automatically or
calls the read gateway for a mutation. See [the management contract](portal-management.md).

`account local` and the TUI's job chooser reuse the native association reader to
list only the current Unix user's accounts. The chooser does not load Portal
membership or infer storage paths. Its [contract](../contracts/native-accounts/v1/README.md)
keeps discovery and query authority explicit. Local quota selects a real path
with Textual's directory tree, then invokes the existing bounded Lustre read.

The optional native job subtree selector uses Slurm's `WithSubAccounts` and
Lineage, bound to the local cluster. It narrows one queue request to those
accounts and verifies returned scope; it neither duplicates account hierarchy
nor consults Portal. Plain native account filters remain exact.

Local quota resolves the chosen path's native project ID and reads explicit
Lustre counter/grace fields as that user. It shares only native process/context
and presentation primitives with other local queries. It does not import the
gateway's mount bindings, grants or storage administration adapter; those solve
the separate remote authorization problem.

## Current and target paths

Users choose the compute site; connectivity configuration selects a route to
that same site. The center owns identity, authorization and final business
facts, without being a required transit point for every site's native reads.
Sites may have separate HTTPS ingress or share one ingress with fixed hostname
routing. The [site topology decision](site-local-read-plane.md#explicit-site-selection-and-ingress-topology)
records the target and current implementation gaps; it does not change the
basic release's remaining real-user acceptance.

Registered job location is an independent `jobs.placement` read, disabled until
the site explicitly approves its disclosure. The site joins one native
allocation to a signed, operator-published inventory and returns only that job's
nodes. Batch CLI, WebUI and Pilot consume `jobs.placement/v1`; no client queries
inventory files or infers current hardware identity from a node name. Static
registration, live allocation, measured utilization and final cost remain
separate facts. See [the contract](../contracts/job-placement/v1/README.md).

The current code release uses control-plane job visibility and
running-estimate read APIs, plus the published site resource catalog.
The catalog shares Portal's WebUI presenter and appears under
`published_catalog` in Pilot's existing resource tool; Pilot's scheduler
preparation metadata remains a separate part of that tool response.
Storage has two explicit contracts: central business quota observations and
on-demand native quota subjects through the site gateway. Both use existing
Portal storage visibility; native reads never import a storage administration
adapter into the CLI or present a physical project quota as a whole funding pool.
The CLI obtains credentials from Identity device authorization or an explicit,
process-local Identity access token. It does not request Portal-issued tokens
or restore their old cache entries. Managed capability/CLI routes accept only
SAI Identity-issued resource tokens:

```text
user -> sai-cli -> SAI Identity device authorization and refresh
     -> Identity access token -> Portal resource API -> authorized site reader
```

Published resource-catalog reads end at Portal's stored product projection;
they do not invoke the site reader.

The resource catalogue has only a site context; job account/state filters do not
apply. It is a batch read of published specifications and prices. Pilot owns
the Web computation-preparation experience. CLI/Agent management must integrate
with the existing validation, pricing, proposal and confirmation services
without embedding that UI or maintaining another resource workflow.

Managed-run reads reuse Portal's existing ComputeRun records and readback
services. The CLI supplies a site and reads only its own runs. Single-workspace reads
require an explicit personal/org/project account; the actor-owned recent-work
reader discovers currently readable account labels in one bounded page. Current ownership or membership/site and CLI read admission are independent of
submission, payer activation and Pilot Session grants. State is a persisted
execution receipt, not a refreshed Slurm queue observation. Metadata includes no
final billing projection. An independent per-Run cost read requires billing
scope and the same account financial visibility as the console. Portal validates
the final graph and exact accounting incarnation; no client prices work or
guesses a scheduler-ID-to-Run relationship.

An explicit per-Run statistics read uses the same current actor/account/site
READ owner. Portal derives native identity and correlation; the existing site-run
helper permanently drops to the site's NSS user before fixed Slurm commands.
Batch CLI, WebUI and Pilot consume one `compute.run-stats/v1` DTO. This is a separate
existing owner-UID execution path, not a privilege fallback for the read gateway.
This remote Run client does not execute Slurm. A separate local native query
must not masquerade as that authorized Run observation. Neither path
reconstructs whole-job utilization from step metrics.

Run placement follows the existing capability gateway, without a new native
helper. Portal derives exact Run/user/account/job/correlation constraints after
current READ; a separate strict grant schema binds the existing allocation and
inventory read. The gateway checks runtime execution and allocation before and
after the observation. A Run wrapper contains the unchanged placement DTO;
ordinary job reads keep their original contract. No consumer may downgrade a
failed Run binding to a plain numeric-job lookup.

Readable task and storage discovery use their respective current ownership/membership
and site authority with bounded SQL pages. Storage shares the quota reader's
membership predicates; it does not inherit compute admission. Only safe names
and exact selectors reach the CLI; the full Web workspace topology, financial
fields and directory paths are not exposed. Exact name resolution narrows the
same directory to one key, without draining pages. Choosing a scope does not
grant any later read or execution, or promise a native quota source is available.

Managed stdout/stderr and output-file metadata require current applied file READ
permission for the Run's frozen mount lineage. They reuse the existing dedicated
interactive-read site adapter; this is a Portal-brokered read, not a new direct
site capability. The CLI never receives that credential. The two file methods
use bounded HTTP responses and refuse redirects. The artifact list represents
current files under declared output roots, not immutable results or file-content
permission. Native Pilot preview keeps its separate owner.

The target remote-site path separates authorization from the query hot path:

```text
                                  +---------------------------+
user -> sai-cli -- bootstrap ---> | SAI capability issuer     |
  |                               | identity + policy + scope |
  |                               +---------------------------+
  | short-lived, site-bound capability
  v
site-local read gateway -> native scheduler/storage readers
  |
  +-> bounded DTO + freshness + asynchronous audit reference
```

Command intent and authorization scope stay stable. Explicit direct-job mode
now consumes the versioned gateway `jobs/v1` DTO rather than silently translating
it into the Portal envelope: the signed grant has no membership role to invent.
The existing Portal JSON contract remains the default. The transport code is
locally tested; service deployment and live-site validation are separate gates.

For current remote API reads, the bootstrap is a one-time OAuth/OIDC
Device Authorization Grant at `sai-identity`: the browser authenticates and
approves the device, while the CLI keeps only a rotating, revocable refresh
credential. A short-lived Portal-bound access token is renewed automatically;
Portal still enforces its audience/scope and CLI read policy. SSH session
reconnects therefore do not require another login.

## Current remote-read trust model

1. SAI Identity authenticates the user and issues a token for the Portal
   resource. Portal then resolves a user-facing scope into an exact scheduler
   user or account filter.
2. The CLI can only request a documented scope and can only narrow state,
   partition, object ID, and result-limit filters.
3. A site reader receives an already authorized filter or a signed capability.
4. Results are filtered again and normalized before they reach the CLI.
5. The CLI validates the normalized contract and fails closed on malformed
   payloads. It never falls back to a broad native scheduler query.

The following facts are deliberately independent:

- identity and account activation;
- command-line access;
- workspace membership and role;
- site access;
- job visibility;
- job mutation rights;
- billing visibility.

Being allowed to view a job does not imply permission to submit, cancel, hold,
requeue, change QOS, or see wallet and ledger data.

## Scope model

The first client supports these scopes:

| CLI scope | Server meaning | Selector |
| --- | --- | --- |
| `self` | Jobs owned by the current scheduler user | No account selector |
| `personal-account` | Jobs charged to the actor's personal compute account | One workspace key, account name or account ID |
| `org-account` | Jobs charged to an organization account the actor may view | One workspace key, account name or account ID |
| `project-account` | Jobs charged to a project account the actor may view | One workspace key, account name or account ID |

Native self activity and recorded Run history are separate bounded reads.
The actor-owned `compute.my-runs/v1` operation joins existing Runs to the
readable-workspace relation and supplies authorized names in one SQL page,
without project fanout or a new task store. The gateway can resolve only visible
current SLUIDs to native database indexes in one bounded batch. Each later
detail/file/cost read reauthorizes. Business and native account IDs stay distinct.

The additive [correlation contract](../contracts/managed-run-link/v1/README.md)
remains in the shared models for consumers that need it. It does not establish
immutable accounting identity or authorization; a job number alone never links
records. The retired terminal's local grouping and work-state machinery are
removed. Pilot owns native Web work and sessions.

The compact summary instead reads the existing account overview. It uses the
applied login account or normal server-resolved overview context, independently
of job filters and file authority. `--account` changes the view, not submission
context. It makes no native job/history reads to populate a home screen.

There is no normal-user `all`, `ops-all`, raw `--user`, or unrestricted raw
`--account` mode. Administrative fleet views belong to a separate management
surface with separate authentication and audit policy.

### Server-bound CLI surface

The legacy Portal job endpoints use the control plane's `portal_read`
entrypoint. That entrypoint rejects disabled shell access but intentionally
allows an `agent_only` account for non-login-node read surfaces. The endpoint
is not a login-node CLI contract.

Managed capability mode uses a dedicated Portal issuer and `/cli/` routes.
Portal resolves the actor with `entrypoint=cli`, enforces shell access
`enabled`, signs a site/operation/filter-bound `sai-authz` envelope, and checks
the Bearer actor and grant again on the read route. A client header alone is
never trusted. This closes the code-level surface gap only after the matching
Portal slice, runtime dependency, signing key/epoch, and CLI package are
deployed and live-tested; local/fake tests do not close those operational
gates.

## Data and consistency

Current job state is a site-local, near-real-time fact. Authorization and
account ownership are control-plane facts. A response therefore carries both
data and freshness metadata.

The client treats these states differently:

| Condition | Client behavior |
| --- | --- |
| Valid response | Validate, then emit JSON or table output |
| Source unavailable | Return a bounded unavailable error |
| Contract invalid | Return a contract error; do not print the raw response |
| Authorization denied | Return a permission error; do not retry with a broader scope |
| Capability expired | Stop protected reads and follow the existing bounded renewal policy |

Historical accounting and final billing are separate products. A settled
ledger is not a substitute for the live queue, and a running-cost estimate is
not a final charge. The CLI receives the estimate from Portal; displaying the
published price catalog does not make it a local pricing engine.

Running estimates remain an explicit batch read. The account summary uses its
own server-authorized exposure facts; it never sums a truncated job list.
A failure in either source must not fall back to a broader read.

## Security invariants

- Bearer tokens and refresh credentials never appear in command-line
  arguments, JSON output, table output, logs, or exception messages.
- HMAC credentials and their retired profile/environment settings are rejected
  before any request; missing authentication directs the user to `sai auth login`.
- OIDC refresh credentials are opaque, rotating, user-owned secrets; they are
  never sent to Portal read routes or stored in the TOML profile.
- Token caches are user-owned, use a `0700` directory and `0600` file, and are
  replaced atomically.
- Plain HTTP is rejected except for loopback development endpoints unless the
  user makes an explicit development-only override.
- HTTP error bodies are reduced to a bounded code/message pair. HTML, raw
  provider responses, native command stderr, and unknown nested fields are not
  echoed.
- Response models use an allowlist. Work directories, output paths, scripts,
  environment variables, credentials, wallet data, and raw scheduler objects
  are never forwarded by the client.
- Filters are validated locally and validated again by the server. Local
  validation is ergonomics, not an authorization boundary.

## Package boundaries

The batch CLI has no third-party runtime dependency. It uses Python 3.11+
standard-library HTTP, JSON, TOML and filesystem primitives. The optional
`tui` extra contains Textual and Rich. The focused query app owns keyboard,
selection and display state only. Native observations, resource renderables,
account discovery, overview and cost contracts retain their existing owners.
A single bounded reader coalesces refreshes; obsolete responses cannot repopulate
a different view. One Textual timer schedules only the visible query; it neither
runs overlapping reads nor adds a daemon, credential store, authorization resolver
or native parser. Local startup precedes remote configuration/authentication.

`sai status --format tui` stays a one-shot Rich summary, including at login.
`sai tui` explicitly launches the interactive app; redirects are rejected with
an actionable diagnostic. Plain and JSON commands do not import Textual.

The implementation is organized around explicit boundaries:

```text
sai_cli.config       configuration and profile resolution
sai_cli.cache        protected token cache
sai_cli.auth         bearer selection and compatibility token exchange
sai_cli.transport    bounded JSON-over-HTTP transport
sai_cli.client       Portal endpoint mapping
sai_cli.contracts    stable response validation and serialization
sai_cli.render       JSON and table presentation
sai_cli.cli          command parsing and exit-code policy
```

Local native adapters and remote API clients keep command handlers thin.
Parsing and normalization belong to the corresponding source adapter;
authority remains with the native system or the API's domain owner.

The gateway server is a separate low-privilege site-runtime role that reuses
the existing site Slurm read adapter and normalized DTO. It is not packaged in
the CLI wheel. This repository owns the client transport and shared protocol
fixtures. Local CLI integration should reuse existing native helper/parser
logic where applicable, without importing the gateway service, its credentials
or a second copy of the same reader into the client.

## Controller Submission Policy Artifact

The repository separately owns `site/slurm/job_submit.lua`. This controller
artifact validates native Slurm submissions; it is not imported by `sai-cli`,
does not enter the client wheel, and does not turn the client into a scheduler
writer.

The plugin consumes a controller-local Lua snapshot generated from a strict
control-plane projection. Portal owns account, membership, project-shape and
policy facts; the site artifact owns bounded submit-time evaluation. The
callback never calls Portal, the site-local read gateway, an authn relay, a
database, or shared storage. Full policy, snapshot and rollout semantics are in
[job-submit-policy.md](job-submit-policy.md).

## Validation boundaries

The separate `site/modules/software_access.tcl` artifact reads only the current
process's numeric groups and a published software/GID definition. It does not
call the CLI or implement Portal grant policy. Portal and the site executor share
one package-owned access definition; native software file permissions remain the
execution boundary. See [software module access](software-access.md).

- Unit and CLI contract tests prove parsing, mapping, caching, redaction, DTO
  validation, and rendering only.
- A local fake HTTP server proves request/response integration only.
- A control-plane development-stack run proves compatibility with that stack;
  it does not prove a live scheduler or remote-site gateway.
- A live read-only canary must separately record the site, authorized scope,
  exact filters, scheduler comparison, package version, and rollback boundary.
- Production wrapper rollout is a separate deployment operation.

## Task output content

The existing managed file authority resolves a selected output reference from
one current list page, checks Run READ and independent applied directory READ,
and uses the existing site reader as the Run owner. CLI, Web and the internal
Agent read API share `compute.run-artifact-content/v1`. No new file service,
authorization store, archive or native CLI fallback is introduced. File-version
byte cursors prevent combining sections after file changes; UI text rendering
never executes markup. See [the content contract](../contracts/managed-run-content/v1/README.md).

Full-file downloads obtain a separate version-bound grant from the same current
Run/file authority. The CLI sends only this short-lived capability to the
grant's fixed site-files HTTPS endpoint, never the Identity Bearer. Binary ranges
are checked against the original version and size; renewal cannot select a new
file. Local output is published atomically without replacing an existing path.
No transfer state or capability is persisted. This source contract requires a
paired Center/site release; text preview and full downloads have separate limits.

### Organization scope compatibility

Remote organization reads include Portal-authorized project subjects, each with
its own user restriction. The versioned grant and DTO changes are described in
[the shared API contract](portal-api-contract.md#organization-job-scope). Native
`sqa` remains a separate Unix-authorized read; its hierarchy is not business
authorization. Deploy gateway and CLI/Pilot readers before the Center issuer;
exact Run, self, personal and project contracts remain unchanged.

## Shared job topology

Local `jobs local --job-id ID`, TUI Enter and gateway job allocation share the
canonical native Slurm projection. Node CPU IDs, socket/core/thread dimensions
and configured GPU count extend the existing allocation contract. Web/Pilot
consumes that same DTO. Local reads do not use OAuth or the gateway. See the
[native allocation contract](../contracts/native-job-allocation/v1/README.md)
for call bounds, provenance and unknown semantics. The shared CLI and site gateway were deployed on 2026-10-11 and checked with
an ordinary user. The paired Web/Pilot source is merged; its production
activation remains with the original Pilot release. Focused polling and account
selection reuse the client reads described in [terminal scope](terminal-scope.md#focused-query-interaction).

The [interconnect contract](../contracts/node-interconnect/v1/README.md) joins recorded CPU/NUMA, PCIe, GPU and fabric
relationships to an exact live allocation via `--with-interconnect`. Local reads
stay native; the existing site gateway uses `include_interconnect=true`.
Deployment and its validation boundary are recorded in
[terminal scope](terminal-scope.md#interconnect-correction-2026-10-12).
