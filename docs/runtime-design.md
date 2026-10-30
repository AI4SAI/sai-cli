# Runtime Design

Status: HTTP/native queries and the first management action are deployed.
The default-account change/restore flow is verified on an independent Linux
client; broader management and platform coverage remain open.

## Target execution model

The 2026-10-09 product clarification makes this a human-and-Agent client.
Integrate the existing SSH aliases and native helpers for low-latency queries on
login/compute nodes. Those native operations use the current UID and site;
configuration for a Portal URL, an OAuth token or a site capability must not be
a prerequisite for their execution. Local observations and human/JSON output
share a native source; they do not scrape one another's presentation.

Account, organization/project, budget, policy and management operations use
Portal domain APIs in all deployment environments. Agents on user devices or
dedicated isolated VMs use the same typed operations and per-user authorization,
without Pilot activation. Remote site observations retain narrow capabilities.
Local job dispatch now runs before HTTP/config/auth prerequisites. Remote
commands retain their existing client and authorization setup. Module loading
follows the same boundary: native queries load only their source, shared job
values and presentation, without loading authentication or remote product clients.

Preserve the explicit HTTP read contracts during migration. `sai jobs local`
implements the existing job-helper filter semantics through Slurm JSON.
The explicit `--with-subaccounts` mode resolves the local cluster and native
Slurm `WithSubAccounts` hierarchy before that one queue read. `sqa`/`ja` use it
so current-organization queries include child projects. Exact `-A` reads add no
metadata query. The
[native contract](../contracts/native-jobs/v1/README.md) records names, flags,
units and failure limits. `resources local` reuses the same native execution/value
boundary for one per-node `sinfo` response; its [contract](../contracts/native-resources/v1/README.md)
separates effective capacities, allocations, blocked resources and reported
metrics. `storage local-quota [PATH]` uses native path metadata and exact Lustre
selected fields with the same bounded subprocess runner; see its
[contract](../contracts/local-quota/v1/README.md). Shared shell migration has
passed bounded ordinary-user checks in [terminal scope](terminal-scope.md);
it does not expand authentication scopes.
Remote errors must not cause a silent source or authority change.

The first management action uses the existing default-account preference:
`account defaults` discovers site choices and projection receipts;
`account set-default` submits a global change with the caller's last saved value
and request key. It requires independent `sai.compute.defaults.write` consent.
Global writes require no site selector; the account discovery read does.
Neither uses the site-read gateway, a Pilot session or a shell-enabled grant.
Source support does not establish live scope registration or site application.
`sai describe` now distinguishes implemented reads, native prerequisites,
local-file writes, session writes and business operations. Exact paths expose
argparse-derived syntax and static scope/readback prerequisites. The descriptor
runs before config/auth/native initialization and does not authorize a caller.
[cli.describe/v1](../contracts/cli-description/v1/README.md) owns this offline
protocol; command handlers retain configuration and semantic validation.

`sai skill` exposes the single official Agent skill bundled as runtime package
data. Its default `cli.skill/v1` JSON contains the client version, skill name and
Markdown content; `--format markdown` exports an installable `SKILL.md`. It reads
only that packaged resource before configuration/authentication initialization.
There is no skill download, installer, host configuration or separate command
registry. The [first-use guide](getting-started.md) explains installation and use.

## Current implementation

The terminal presentation follows [terminal scope](terminal-scope.md).
Native helper tables preserve the original alias presentation: fixed job columns,
native GPU IDX cells and partition bars, CPU/memory allocation bars grouped by
partition, and quota usage/limit/grace columns. `stat_gpu` and `stat_cpu` include
nodes by default. Resource tables use the existing optional Rich UI dependency;
JSON/native readers remain dependency-free, with no additional native query.
The combined resource summary shows each partition's free/total GPU, CPU and
memory and each resource's largest free amount on one node. These independent
maxima do not describe one combined allocation. Totals deduplicate shared nodes;
CPU totals include the CPUs on GPU nodes. The shared login status fragment uses
this summary from one native observation, followed by the current-directory
quota. Explicit GPU/CPU helpers and the native status alias keep node details.
With no subcommand, `sai` uses the same central account read: plain text when
stdout is a terminal, JSON when redirected. It returns without prompting and
needs no optional UI package. This changes presentation only; it adds no native
query, site grant or automatic device login. Explicit commands keep their format
defaults and existing argument-order contract.
`sai tui` provides focused Textual query interaction; `sai status --format tui`
keeps the one-shot summary and returns to the shell. The shared replacement was selected on 2026-10-07; bounded ordinary-user
and SSH/PTY evidence is recorded in the scope decision, separately from human
usability acceptance.

## Project member management candidate

The `projects` group adds bounded names/member discovery, exact member preview,
`enable-compute` with explicit `--apply --request-id`, and original request/task
readback. It uses independent optional collaboration scopes through the central
API and never the native query or site-read gateway. Effective compute states
share the Web reader; file roles and membership validity are preserved.
Candidate implementation and local evidence do not establish paired activation.

## Command surface

`invitations list/show/accept` are global recipient operations: the returned
invitation carries its target site and current terms. They reject explicit
site/cluster selectors, use normal Identity and Portal, and require no native
tools, shell-enabled account or read gateway. `accept` previews by default using
read scope; `--apply` rereads the exact v2 invitation and performs one POST with
its explicit computation permission, using the separate acceptance scope.
Readback remains `invitations show` with that same ID, including after identity
verification. A required verification returns the existing central account URL
in both JSON and human output; it does not start another device login. JSON and human output
share the allowlisted contract; file access, governance and computation remain
distinct. V2 requires paired activation; see [management](portal-management.md#collaboration-invitations).

`sai sites` needs the central profile and ordinary `sai.compute.read`, but no
site or cluster selection. It lists published site IDs/names from the existing
Portal directory, excluding disabled entries and operational fields. Keyset
pages accept `--limit` and the returned `--cursor`. JSON is the default; table
mode has two columns. The command does not save configuration or probe sites.
It adds no TUI page and leaves the local native command path unchanged.

The CLI exposes local queries, authorized reads and explicit domain management.
Common query examples:

```bash
sai
sai jobs local --format table
sai jobs local -A research --format json
sai status --site site-a --format tui
sai status --site site-a --format json
sai jobs list --site site-a
sai jobs list --site site-a --scope org-account --account org-example
sai jobs list --site site-a --scope project-account --account project-example \
  --states R,PD --partition gpu-standard --limit 100
sai jobs show 12345 --site site-a
sai jobs show 12345 --site site-a --scope project-account \
  --account project-example
sai jobs allocation 12345_0 --site site-a --cluster cluster-a
sai jobs placement 12345_0 --site site-a --cluster cluster-a
sai jobs cost --site site-a
sai jobs cost 12345 --site site-a --format table
sai jobs cost --site site-a --scope project-account \
  --account project-example --states R,PD --partition gpu-standard
sai resources catalog --site site-a --format table
```

`--format json` is the default. `--format table` is intended for a person at a
terminal. JSON is always written to stdout; diagnostics are written to stderr.

Remote API commands do not implement:

- job submission, cancellation, hold, requeue, suspend, or QOS changes;
- normal-user all-site or all-account queries;
- raw scheduler user filters;
- automatic fallback from live state to broad accounting queries;
- full-site asset exports, node topology, utilization or storage management.

Managed-run result reads are shared with Pilot through the independent
`pilot-read-call/v1` operations `run.get`, `run.logs`, `artifact.list` and `artifact.read`.
They use current account READ and the run's frozen output mount, rather than
the submit/cancel execution grant. Web/Agent continuations carry opaque run/artifact references and bounded
cursors under their own client contract. They do not require a TUI flow.
Runtime renewal and model submission remain separate user actions.

`jobs placement` requires the explicit site gateway and an independent
`jobs.placement` capability. It returns the same response's allocation and
operator-recorded registration for only those nodes. Site opt-in is required;
there is no inventory fallback. Ordinary allocation inspection remains
available separately through its existing batch command.

`storage workspaces` discovers authorized personal, organization and project
storage scopes by name at the selected site. It uses independent storage READ,
bounded central metadata and explicit pagination. `--workspace-key` narrows it
to one exact choice and cannot be combined with a cursor. This is a batch
directory read; it does not authorize an account overview or financial read.

`storage quota-summary --workspace-key personal:example` reads Portal's stored
quota observation under the independent `sai.storage.read` Identity scope.
Workspace and site are explicit; this is not an on-demand native storage read.
No site capability, recursive scan, permission change or fee calculation occurs.

`storage native-quota --workspace-key project:example` instead obtains a separate
`storage.quota.read` capability and reads native Lustre quota subjects from the
configured gateway. Its exact byte/inode counters and per-subject observation
times describe physical quotas, not the organization's whole funding pool.
There is no source fallback. Native deployment requires a reviewed readable
filesystem anchor; local code does not enable it.

`sai tui` uses Textual for focus, selection, scrolling and terminal restoration.
Queries invoke the same batch CLI operations and JSON models in a cancelable
child process, with no Shell. Textual cancellation terminates only that process
group, including its native children, then reaps it before returning to Shell.
The initial view is an available local query, or account information on a host
without native commands. `--view jobs|gpu|cpu|quota|account` selects explicitly;
unavailable native tools are reported, never replaced by a remote read.
One current observation feeds each view. Partition selection filters that same
resource observation, preserving GPU indices. Job reads select self or the applied
native account and subtree; account and cost reads initialize the existing
remote client only when requested. A selected cost must match cluster, account,
user, job/task and submission time before display. Native visibility never grants
billing permission. The interface contains no business write or Pilot session handler.
An explicit authorization-recovery key delegates to the installed CLI's existing
login flow; it does not implement another device protocol. Consequently the
interactive command's discovery effect is conservatively `session_write`, while
opening a native view still requires no authorization and starts no login.

Opening the native job selector reads `account local`, sharing the existing
association parser under the current UID. It does not delay the first queue.
Selected accounts use the original subtree filter and cost reauthorization.
Quota offers an explicit native directory chooser, without translating scheduler
accounts to filesystem paths. Choices persist when switching query views.

`r` refreshes, `p` pauses/resumes updates, arrows/Enter or a click inspect a row, and `c` requests a job estimate.
Escape closes the current detail/selection and `q` exits. Job detail holds
keyboard focus and the available content area; arrows
and page keys scroll without changing the selected job. `r` rereads that exact
detail, and Escape restores the original list without a new query. Allocation
details share the batch Rich renderer. The view prioritizes a compact
CPU/NUMA and GPU relationship view, selected-GPU paths and optional hardware
details; exact Slurm IDs remain available without per-thread panels. The compact
tree shows the job's mapped CPU domains and selected GPUs, keeping its placement
ahead of unrelated node hardware. Expansion restores the complete recorded
domains and devices from the same response; unknown locality is never inferred.
Native and business reads are bounded and serialized within each source, with
at most two active reads in total. Repeated requests retain only the newest
pending query; a slow remote read does not delay a newly selected native view.
Changing view/scope clears stale facts before loading. Account names come from
the existing authorized defaults directory and change only the view, not the
saved preference. Native queries do not require a business configuration or login.

The visible query alone polls: jobs 5 seconds, GPU/CPU 10 seconds, native quota
30 seconds and account information 60 seconds, measured from read completion.
An open selector or job detail suspends automatic reads. Node detail refreshes
from the same resource observation without an extra native call. Refresh keeps
rows visible while reading, then preserves selection, scroll and focus; a failed
read clears the stale result and shows its error. Account entry and refresh read
the existing directory and overview serially. Changing the selected account
clears its old facts immediately and never calls the default-account writer.

`sai status --format tui` still prints one Rich summary without consuming stdin,
including from the shared login fragment. Neither command starts device login
automatically. JSON and plain output remain independent of optional UI packages.

Optional TOML `site_read_base_url` selects direct site reads for `jobs list`,
`jobs show` and `storage native-quota`. Missing connection settings for native
reads can instead come from the selected site's `site.connection/v1` metadata.
`jobs allocation JOB_ID` returns the versioned allocation snapshot without a
central fallback. These reads require capability mode; jobs bind the configured
or discovered cluster, while native quota retains its separate workspace grant.
The origin is HTTPS (unmanaged loopback HTTP for local tests); no argv or
environment override is accepted. Managed installations use the existing
protected configuration, not a new per-command mount or file hierarchy.

Resource preparation belongs to Pilot. The terminal catalogue remains an
explicit read of published facts; it no longer constructs browser preparation
URLs or maintains resource selections/comparisons.

The gateway receives only a short-lived `X-SAI-Capability`; the Identity Bearer
stays at Portal. Results use the explicit `jobs/v1` envelope, including subject,
observation time, freshness, ETag and `has_more`, without a fabricated visibility
role. Gateway failures stop the request. The cost/catalog/auth commands keep
their existing central contracts; they do not test a gateway and fall back.
A fixed central-relay profile supplies the selected site and cluster together
in TOML. Supplying a cluster filter to a portable query cannot select that route.
Both job transports bind known account names, state aliases and partitions to
the response before rendering; job lists also enforce their requested limit.
Central running estimates share those filters but retain their complete snapshot
contract without a list limit.

`resources catalog` returns published compute specifications, QOS names,
storage products and prices. It accepts a site and output format, not job
scope/account/cluster filters. Managed mode uses an Identity-only central read
route; no site capability, scheduler read or local pricing engine is involved.
Published capacities are not idle resources or a guarantee of eligibility.
Unknown capacities remain null in JSON and `unknown` in the table.

`jobs cost` calls Portal `GET /v1/billing/running-estimates`. It reuses the
list command's scope and narrowing options, validates the independent
`billing.running-estimate/v1` DTO, and renders it without local caching,
scheduler access, or price calculation.

The batch cost command remains an explicit inquiry, independent of the account
overview. The terminal does not join estimates to another queue observation or
price jobs locally.

The controller-side `site/slurm/job_submit.lua` artifact does not change this
client boundary. It validates jobs submitted through native Slurm commands but
does not expose a `sai jobs submit` command.

Unimplemented command families remain in the roadmap rather than appearing as
placeholders that return fake data.

The legacy Portal endpoint uses `portal_read` authorization and can
accept an `agent_only` account. Managed login-node operation requires
(a) SAI Identity to issue the registered Portal-audience token, (b) Portal to
verify that token and its CLI surface, and (c) the server-verifiable CLI
surface to enforce shell access `enabled`; client headers or local checks cannot
establish that authorization boundary.

## Scope selection

### Managed tasks

`runs placement RUN_REF` uses current account/site READ.
`compute.run-placement/v1` wraps one verified native execution and the existing
`jobs.placement/v1` result. Site opt-out and allocation/registration authority
remain independent of ordinary job reads.

`runs stats RUN_REF` uses compute READ and the same account/site selectors.
It returns the bounded native observation described in
[the statistics contract](../contracts/managed-run-stats/v1/README.md).
A failed source is not an empty or zero observation.

`runs cost RUN_REF` is an explicit final-cost read, requiring
`sai.billing.read` and independent financial visibility. Missing amounts stay
unknown. See [the shared cost contract](../contracts/managed-run-cost/v1/README.md).

`runs list`, `runs show RUN_REF`, `runs logs RUN_REF` and `runs files RUN_REF`
require `--workspace-key personal:ID`, `org:ID` or `project:ID` and the configured
or explicit site. Each task remains bound to its recorded account. These commands reject an
explicit `--cluster`; each task's recorded cluster is a returned fact. Run
references come from the task list, not from numeric scheduler IDs.

List/file pages accept `--limit` (1–100) and the previous response's `--cursor`.
Logs accept `--stream stdout|stderr`, `--cursor` and `--max-bytes` (1–65536).
JSON remains the default; table mode displays log control bytes as escaped text.
JSON also escapes terminal control ranges while preserving decoded content.

`runs recent` uses a site, limit and cursor. The client can also narrow the same
reader to up to 100 exact Run references from visible native records; the server
repeats actor/site and optional workspace checks. This closes old-running-work
discovery without per-Run native reads or history scanning. Its `compute.my-runs/v1`
rows include authorized workspace labels and exact keys for subsequent reads.
The server fixes the actor and joins currently readable workspaces once; the
client does not enumerate projects. A revoked cursor requires a fresh page.

Task, file, cost and storage permissions remain separate. Removing their
workbench views does not change the batch contracts or authorize one read
through another domain's scope.

### Scheduler jobs

`jobs charges [JOB_KEY]` reads settled computation expenses from Portal.
Without a key it returns one bounded page; `--job-id` narrows discovery and may
match more than one historical execution. With a list-returned key it reads
exactly that accounting record. `--start-date` and `--end-date` filter settlement
dates in the selected site's billing timezone. JSON retains full decimal
precision; table mode gives a compact page or the existing final-cost details.
The operation uses only Identity billing scope and current financial authority;
it does not inherit cluster, live-state, site capability or shell prerequisites.
`jobs cost` remains the explicit non-final running estimate.

`--scope` accepts `self`, `personal-account`, `org-account`, or
`project-account`.

- `self` rejects account selectors.
- `personal-account`, `org-account`, and `project-account` require exactly one
  of `--workspace-key`, `--account` or `--account-id`.
- A workspace key supplies the account kind when `--scope` is omitted. An
  explicit scope must match that kind; explicit `self` cannot take a workspace.
  Portal resolves the business key to its native account under the original READ
  policy. The client never uses the workspace suffix as `--account-id`.
- The CLI maps hyphenated user-facing values to the control-plane underscore
  values. The server remains authoritative.

`--states` is a comma-separated allowlisted token list. `--partition` only
narrows the result.  The running-estimate endpoint deliberately returns the
complete authorized live snapshot and has no client `--limit` parameter.

## Configuration

`sai configure SERVICE_URL` reads `/v1/auth/config?client=sai-cli` anonymously,
checks `cli.connection/v1` and the issuer's existing OIDC discovery, then creates
the selected user TOML through non-overwriting atomic publication. It preserves
existing credentials, profiles and scope baselines. Matching repeat calls only
verify; a different existing configuration requires a separate `--config` path.
The managed shared wrapper rejects this local configuration operation. No login,
API permission check or site selection happens during configuration.

Configuration precedence is:

1. command-line non-secret options;
2. environment variables;
3. the selected TOML profile;
4. built-in non-secret defaults.

Default config path:

```text
${XDG_CONFIG_HOME}/sai/config.toml
~/.config/sai/config.toml
```

Example:

```toml
default_profile = "default"

[profiles.default]
base_url = "https://portal.example.org"
identity_issuer = "https://id.example.org/realms/sai"
oidc_client_id = "sai-cli"
oidc_scope = "openid offline_access sai.compute.read sai.billing.read sai.storage.read"
oidc_resource = "sai-portal"
site_id = "site-a"
timeout_seconds = 10
```

Tokens and secrets are rejected in TOML. Device credentials use the protected
user-owned cache; an explicit Identity `SAI_TOKEN` is process-local. Retired
HMAC environment variables and TOML `username`/`key_id` fields are rejected,
including when a valid `SAI_TOKEN` is also supplied.
The diagnostic names the old inputs to unset or remove before running
`sai auth login`; an explicitly present empty variable is also rejected.

Relevant environment variables:

| Variable | Purpose |
| --- | --- |
| `SAI_API_BASE_URL` | Control-plane base URL |
| `SAI_SITE_ID` | Default site |
| `SAI_PROFILE` | Profile name |
| `SAI_TOKEN` | Already-issued short-lived Identity access token for this process |
| `SAI_API_TIMEOUT` | HTTP timeout in seconds |
| `SAI_CREDENTIAL_CACHE` | Optional unmanaged path for the protected device session |
| `SAI_IDENTITY_ISSUER` | SAI Identity OIDC issuer used by `sai auth login` |
| `SAI_OIDC_CLIENT_ID` | Pre-registered public OIDC client identifier |
| `SAI_OIDC_SCOPE` | Reviewed OIDC scopes for the Portal resource (includes `offline_access`) |
| `SAI_OIDC_RESOURCE` | Optional Portal resource/audience identifier |
| `SAI_ALLOW_INSECURE_HTTP` | Development-only explicit HTTP override |
| `SAI_REQUIRE_SITE_CAPABILITY` | Require the server-bound capability/CLI routes; mandatory in managed production wrappers |

## Authentication

Follow-up commands retain explicitly selected config/profile, service origin and
connection options at the CLI presentation boundary. Missing-session and scope
errors, device resume, site pagination, account readback and the focused TUI
reuse this renderer. Domain errors describe the recovery action without owning
shell syntax. JSON error codes and authentication requests remain unchanged.

Token selection order is:

1. use an explicit Identity `SAI_TOKEN` for the current process without writing it to disk;
2. reuse a valid CLI device access token;
3. rotate a valid SAI Identity OIDC refresh credential at the discovered
   `token_endpoint`;
4. return `credentials_unavailable` and direct the user to `sai auth login`.

Legacy bearer cache entries are ignored. The client never calls Portal's retired
HMAC token endpoint. `SAI_API_USERNAME`, `SAI_API_KEY_ID`, and
`SAI_API_SHARED_SECRET` are no longer supported.

`sai auth login`
uses a short-lived browser/device authorization and persists the resulting
access/refresh pair as one protected device session. The CLI must not accept a secret, Bearer token,
or refresh credential as a command-line argument because process listings and
shell history are not secret stores.

For managed production use, Bearer authentication is followed by a capability
exchange at `POST /v1/authz/site-read` with the exact JSON request body. The response is cached as an opaque
short-lived credential keyed by the user-session digest, operation, site,
scope, exact filters, and job ID. Jobs and running-estimate reads then use
`/v1/slurm/cli/...` or `/v1/billing/cli/...`; the server revalidates both the
Bearer actor and the signed grant. A cached Bearer or capability is refreshed
at most once after authentication failure.

## Token and device credential caches

The configured scope baseline stays part of the credential key. Explicit
`auth login --for` consent can extend the same profile's session without writing
TOML or selecting a different origin. The existing protected pending/refresh
records carry requested/granted scope metadata; no extra registry is introduced.
Pending or under-granted consent preserves the old login. Refresh uses an
explicit returned scope, or retains the known grant when omitted; legacy scope
metadata remains unknown. Business permission remains server-owned.

Disposable site-capability cache path precedence is:

```text
${XDG_RUNTIME_DIR}/sai/token-cache.json
${XDG_CACHE_HOME}/sai/token-cache.json
~/.cache/sai/token-cache.json
```

Requirements:

- directory mode `0700`, file mode `0600`;
- no symbolic-link cache files;
- atomic same-directory replacement;
- device entries bound to the Portal base URL, Identity issuer, public client
  ID, resource, scope and credential kind;
- a token is considered expired before its actual expiry to leave request
  margin;
- malformed or weak-permission caches fail closed with a bounded diagnostic.

The persistent device session defaults to
`${XDG_DATA_HOME}/sai/credentials.json` or
`~/.local/share/sai/credentials.json` and has the same `0700/0600`, symlink,
atomic-replacement, and ownership requirements. Access, refresh and granted scope
are committed in one atomic replacement under the existing per-user lock.
SSH runtime-directory removal does not discard a still-valid access token.
The lock wait is bounded by the effective API timeout. Old refresh-only records
are upgraded on the next normal renewal; old access-cache entries are not used
as an authentication fallback. Pending device requests keep their existing keys.

Only an explicit rejected refresh credential clears that session, inside the
same lock. Discovery, transport, response and storage errors preserve the current
record. A stale access rejection invalidates only its matching lease. Ordinary
SIGINT/SIGTERM during refresh are honored after its response has been validated
and the updated session saved, before any subsequent business operation.
Remote TUI cancellation allows `2 * timeout_seconds + 5` seconds for this
bounded exchange; native child cancellation retains its one-second grace.
SIGKILL, a lost token response and unavailable storage cannot guarantee recovery.
This changes neither issuer expiry nor server revocation behavior.

Shared activation must let old in-flight calls finish. The original refresh key
remains readable by the prior client, but a rollback to that authentication code
needs separate verification: it may consume a retained legacy access entry.
Never restore a backup containing an already-consumed refresh token.
Previously issued access tokens remain subject to the issuer's actual expiry
and resource-server checks, including across older processes or devices.

Refresh expiry may be unknown: OAuth does not require an expiry extension, and
some providers return zero for server-managed offline sessions. Only refresh
credentials may store an explicit null expiry; access tokens and pending device
codes still require a finite expiry. Unknown expiry does not imply permanent
validity: the issuer enforces idle limits, revocation, and account state.

Managed `/opt/sai/cli/config.toml` additionally requires a root-owned regular
file beneath root-owned, non-group/world-writable, non-symlink directories.
This applies only to the managed path; XDG paths retain per-user rules.

## HTTP behavior

- The base URL must be HTTPS unless it resolves syntactically to a loopback
  host or the development override is explicit.
- Requests have a bounded timeout and response-size limit.
- Each request carries a client-generated request ID.
- Redirects are not used to broaden trust to another host.
- Non-2xx responses are mapped to stable CLI error categories.
- Only a bounded server `detail.code`, `detail.message`, or string detail is
  eligible for display, after secret-pattern redaction.
- A non-object JSON payload is a contract failure.

## Output contract

JSON output contains only the stable job visibility or running-estimate fields documented in
[portal-api-contract.md](portal-api-contract.md). Unknown response fields are
ignored after validation instead of being copied to stdout.

Running-estimate table output leads with the authorized scope, job and prices.
With a job ID, the existing priced-detail response is used instead of a list.
JSON retains the normalized job envelope with `items[0].running_estimate`;
its timestamps remain UTC, which the human view labels with `+00:00`.
It labels the amounts as unsettled, distinguishes standard price from cash
before Credit, and prints unknown/not-started/restricted states instead of zero.
It never adds the two prices or combines them with settled charges. It shows
`as_of`, observation time, source and age, with a prominent stale warning.
ETag, exact quantities and other protocol details remain in unchanged JSON.
Full-scope list times use the response's required site/Slurm
IANA timezone and show an explicit offset, never the center or terminal local
timezone. A pending job has no zero-cost claim; an
unavailable estimate has no guessed amount. Both remain explicit row states.

The cost table fits the terminal where possible and expands into labeled rows
when the columns do not fit. Identifiers, monetary values and uncertainty
reasons are never clipped; very long values can wrap in the terminal. Redirected
output uses a deterministic 80-column layout with no optional UI dependency.

Table mode keeps the established SAI meanings:

- `GPU` is GPU count per node, not total GPU count.
- `MemPerU` is host memory per GPU or CPU logical unit.
- `Slots` can describe requested tasks while pending and allocated CPU slots
  while running.
- `Reason/Nodelist` is a pending reason or the allocated node expression,
  depending on state.

Table rendering uses no ANSI color by default so redirects and wrapper output
remain deterministic.

Overview, current-job estimates and final Run costs share a decimal presenter
for human views: two amount decimals, four quantity decimals and grouped digits.
Credit and quantities omit trailing zeroes. Values below the normal display
precision retain their exact necessary digits and sign; unknown values stay
unknown. Display rounding is half-up, never binary-float arithmetic, and does
not alter the server strings retained in JSON or calculate a new price.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | Command or configuration error |
| `3` | Authentication failed or credentials unavailable |
| `4` | Authorized identity lacks the requested permission |
| `5` | Object not found or not visible |
| `6` | Authorized source temporarily unavailable |
| `7` | Server/client contract invalid |
| `8` | Network or timeout failure |

In JSON mode, errors are emitted as a small JSON object on stderr. In table
mode they are emitted as one plain diagnostic line.

Errors with a known recovery action additionally expose `error.recovery.argv`,
an argument array beginning with `sai`. It uses the same connection-context
builder as the copyable human command; Agents need not parse shell text from
`message`. Pending `auth login --no-wait` results similarly include `resume_argv`
alongside the existing human `resume` command. This is a suggested action, not permission to execute it or an
automatic retry. `SERVICE_URL` remains a placeholder for a user/operator-provided
trusted address. Authentication for a known task uses the installed operation
scope metadata, including readback. Ordinary network, storage and business
denials do not acquire login actions. Managed recovery uses the shared profile
and omits transient invocation limits such as the automatic summary's timeout.
An explicit `--no-cache` without a process-local token reports
`device_session_disabled` without a login action: signing in would not make the
original cache-disabled invocation able to use that session.

The TUI retains the child's error code, request ID and recovery arguments. An
account-directory failure hides the empty chooser and shows the actionable
error at the start of the content; native tabs remain available. Existing
authorized choices remain visible if only the selected account read fails.
On supported terminals, `l` suspends Textual and runs only the bound `auth login`
action through the same installed CLI, preserving its profile and task scopes.
Normal browser consent remains required. Success refreshes the original view;
failure or cancellation retains its context and real error. Opening the view
does not request authorization. Other recovery commands, including configuration
placeholders, remain manual; this is not an arbitrary command executor.

## Existing helper and alias integration

Existing native helpers and aliases are the starting point for local queries.
Reuse their implementation, or migrate it once into a shared native adapter.
After a helper is replaced, its wrapper only translates the familiar name and
flags and selects human output; do not retain two competing query engines.
Native queries keep the caller's Unix authority, without wrapper-owned policy.

The rollout sequence is: inventory and checksum, stage the new package, canary
through an explicit path, atomically switch package-managed wrappers, validate,
and retain a package-level rollback. This repository does not authorize manual
editing of production command directories.

## Direct output inspection

`runs read` consumes the same current UTF-8 content DTO as
the console and internal Agent API. Each request returns at most 64 KiB, with byte
positions, observed time and a native file version. A changed, missing or unsupported
file contains no preview text. Back restores the prior file-list cursor; refreshing
starts a new observation rather than combining old/new content. JSON preserves
exact counters and text; terminal output escapes controls. Full-file download uses
the separate contract below. Native Pilot tool registration remains separate
work, not implied by the read endpoint.

## Save a complete output file

```bash
sai runs download run-example --workspace-key project:example \
  --artifact-ref artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --artifact-cursor 100 --output result.bin
```

The artifact reference and optional list cursor come from `runs files`. The
explicit output is a local filename, never a server path. The client acquires a
short-lived, version-bound download grant from Portal, then sends only its
capability to the fixed site-files endpoint. Reads use at most 8 MiB per range;
status, length, range and ETag must agree with the original file version/size.
An expired capability permits one new grant per failed range, pinned to that
same version. Redirects and non-loopback HTTP are refused, including when the
general development HTTP override is enabled.

Bytes go into a private `0600` temporary file in a random `0700` subdirectory of
the destination directory. The client holds that private directory by descriptor
so another writer to a shared destination directory cannot replace the source.
After complete-size verification and file sync, a hard link publishes the file
atomically without replacing an existing file, directory or symbolic link.
Failure or interruption removes the current temporary file and directory. No capability or
resume metadata is saved; a new command starts from the beginning. Successful
JSON contains only workspace/site/Run/artifact references, the chosen local
output path, complete byte count and version. The batch CLI still needs no
third-party runtime dependency. Paired server deployment is a separate gate.

### Organization scope compatibility

Remote organization reads include Portal-authorized project subjects, each with
its own user restriction. The versioned grant and DTO changes are described in
[the shared API contract](portal-api-contract.md#organization-job-scope). Native
`sqa` remains a separate Unix-authorized read; its hierarchy is not business
authorization. Deploy gateway and CLI/Pilot readers before the Center issuer;
exact Run, self, personal and project contracts remain unchanged.

## Shared job topology

For a capability-based remote query, missing cluster or required gateway settings
are resolved through `site.connection/v1` for the explicit site. Existing fixed
profiles bypass discovery. The same initialization covers native quota; running
cost may resolve a cluster while keeping its central route. Discovery changes
neither the profile nor permissions, and failure does not select another source.
Local commands return before this connection initialization.

Local `jobs local --job-id ID`, TUI Enter and gateway job allocation share the
canonical native Slurm projection. Node CPU IDs, socket/core/thread dimensions
and configured GPU count extend the existing allocation contract. Web/Pilot
consumes that same DTO. Local reads do not use OAuth or the gateway. See the
[native allocation contract](../contracts/native-job-allocation/v1/README.md)
for call bounds, provenance and unknown semantics. The shared CLI and site gateway were deployed on 2026-10-11 and checked with
an ordinary user. The paired Web/Pilot source is merged; its production
activation remains with the original Pilot release. Focused polling and account
selection reuse the client reads described in [terminal scope](terminal-scope.md#focused-query-interaction).

Hardware interconnect is a separate recorded fact, `node.interconnect/v1`.
It is joined only when `sai jobs local --job-id ID --with-interconnect` is
requested, so ordinary allocation JSON remains stable and a missing mapping
cannot look like an empty topology. The record is site-published and time-bound;
it contains verified CPU/NUMA-to-GPU affinity, GPU path classes and safe
node-fabric peer references. The same standard-library record reader and validator
is exported from the Portal producer for the CLI and gateway. Capture parsing
and record construction remain in its operator-only module, excluded from both
read runtimes. Automated collection, refresh, publication and expiry alerts
belong to the separate infrastructure operations project. Pilot adoption remains with its
existing owner. It never runs
remote SSH, treats Slurm IDX as a physical identity, or falls back from an
expired record to a guessed layout.

Optional `cpu_mapping` records Slurm abstract CPU IDs in their native order and
their corresponding Linux CPU IDs, with an observation time. The same normalizer
checks its interval, node dimensions and membership in Linux NUMA domains. A
shared locality projection drives compact job CPU highlighting; missing mappings
do not imply local allocation. The mapping does not measure task execution.
