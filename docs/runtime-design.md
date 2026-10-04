# Runtime Design

Status: read-only commands frozen

## Command surface

The current release exposes read-only job and resource commands:

```bash
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
sai jobs cost --site site-a --scope project-account \
  --account project-example --states R,PD --partition gpu-standard
sai resources catalog --site site-a --format table
```

`--format json` is the default. `--format table` is intended for a person at a
terminal. JSON is always written to stdout; diagnostics are written to stderr.

The first release does not implement:

- job submission, cancellation, hold, requeue, suspend, or QOS changes;
- normal-user all-site or all-account queries;
- raw scheduler user filters;
- automatic fallback from live state to broad accounting queries;
- full-site asset exports, node topology, utilization or storage management.

Managed-run result reads are shared with Pilot through the independent
`pilot-read-call/v1` operations `run.get`, `run.logs`, `artifact.list` and `artifact.read`.
They use current account READ and the run's frozen output mount, rather than
the submit/cancel execution grant. A console or TUI file continuation carries
only an opaque run/artifact reference and a bounded page cursor. The task page's explicit action opens original history directly; file previews
and prompt insertion remain separately authorized. Runtime renewal and model submission remain
separate user actions.

`jobs placement` requires the explicit site gateway and an independent
`jobs.placement` capability. It returns the same response's allocation and
operator-recorded registration for only those nodes. Site opt-in is required;
there is no inventory fallback. TUI registration inspection pauses polling and
clears expired metadata independently of its refresh interval, without sending
another request. Ordinary allocation inspection remains available separately.

`storage workspaces` discovers authorized personal, organization and project
storage scopes by name at the selected site. It uses independent storage READ,
bounded central metadata and explicit pagination. `--workspace-key` narrows it
to one exact choice and cannot be combined with a cursor. The TUI uses this
directory in place of a raw-key input; an explicit CLI preselection first
resolves that key's name without selecting a different scope.

`storage quota-summary --workspace-key personal:example` reads Portal's stored
quota observation under the independent `sai.storage.read` Identity scope.
Workspace and site are explicit; this is not an on-demand native storage read.
No site capability, recursive scan, permission change or fee calculation occurs.

`storage native-quota --workspace-key project:example` instead obtains a separate
`storage.quota.read` capability and reads native Lustre quota subjects from the
configured gateway. Its exact byte/inode counters and per-subject observation
times describe physical quotas, not the organization's whole funding pool.
There is no source fallback. The TUI Storage selector uses the same two client
methods and clears old-source results immediately. Native deployment requires
a reviewed readable filesystem anchor; local code does not enable it.

`sai tui` starts with the default-identity Overview and is an optional interactive
consumer of these same read methods.
On managed login nodes, `sai status` and Overview retain the applied login Account;
an explicit `status --account` overrides it, while job and storage scopes remain independent.
It keeps the configured site/cluster fixed, lets users explicitly apply job
scope and narrowing filters, compares published partitions, and shows job
detail, allocation snapshots and independent running estimates. View allocation
uses one response for the job, node CPU/memory, freshness and restart count,
without merging a previous detail response. Inspection pauses automatic refresh;
F5 clears and replaces the full snapshot. Changing object, mode, applied scope
or tab, or pressing Escape, clears the allocation and discards late responses.
Array-task identity includes task zero for both detail and allocation. Allocation
states remain explicit; utilization and physical location are not inferred.
Its dependencies are an optional
extra; JSON batch commands do not import or require them. Interaction and
verification boundaries are in [terminal-workbench.md](terminal-workbench.md).

The terminal derives browse, inspect and summary presentation from its existing
view and selection. This does not add a request, data cache or permission model.
All object inspections share one responsive evidence area and a current-object
heading. Back acts only on the current view. Polling eligibility is independent
of layout: ordinary job/task details can refresh automatically, while allocation,
location, resource, estimate and task-file/log snapshots require explicit reads.
Only eligible views enable F6 and expose Pause/Resume in the command palette.

Open in Web appears after successful job detail or allocation inspection. Its
one-time action uses the same serialized reader to call Identity-only
`GET /v1/slurm/cli/jobs/{job_id}/web-context`; it sends no site capability.
Portal resolves the actual job account's workspace, including a self-scope job
running under an organization or project account. The CLI validates the
`jobs.web-context/v1` mapping and constructs a fixed Jobs link on its configured
Portal origin. Neither the default Overview identity nor account naming supplies
the workspace. The action does not start Pilot or alter the applied job scope.

The link carries the inspected snapshot's observation time, nullable submission
time and nullable restart count as comparison evidence. If both sides know a
submission time or restart count and it has changed, the TUI keeps its snapshot
and asks for a refresh instead of navigating. Job IDs and these timestamps do not
prove permanent execution identity. The browser reauthorizes and reads current
data, independently of the displayed list limit.

The short link remains visible and clickable when the terminal has no local
browser; Copy link explicitly sends the complete URL to the terminal clipboard.
Nothing is copied automatically. Compact buttons remain visible at forty columns.
A opens allocation and W prepares the Web link outside editable controls; the
same context-sensitive actions appear in Textual's native Ctrl+P command palette.
Refresh, scope/object changes and denied reads clear the link. Duplicate clicks
coalesce; late responses after a revision change cannot open a browser, and polling
never requests navigation. A `job_navigation_workspace_denied` response preserves
the authorized self snapshot while explaining that its workspace cannot be opened;
other authorization failures retain the existing view-clearing rules.

Optional TOML `site_read_base_url` selects direct site reads for `jobs list`,
`jobs show` and `storage native-quota`. `jobs allocation JOB_ID` also requires
this setting and returns the versioned allocation snapshot without a central
fallback. These reads require capability mode and an explicit cluster.
The origin is HTTPS (unmanaged loopback HTTP for local tests); no argv or
environment override is accepted. Managed installations use the existing
protected configuration, not a new per-command mount or file hierarchy.

Resource preparation has no new CLI request or write command. The current
validated catalog supplies exactly one candidate, and `preparation_url` creates
`/portal/#/portal/resources/prepare?site_id=...&partition_ref=...` at the protected
Portal origin. It carries neither account guesses, resource quantities, prices,
paths nor prompts. Resources hides Jobs filters, uses Enter for candidate
selection and C for a separate bounded comparison. Refresh, errors and tab
changes clear candidate/link; inspecting a resource pauses polling. View jobs
uses the explicit candidate, independent of comparison order.

The gateway receives only a short-lived `X-SAI-Capability`; the Identity Bearer
stays at Portal. Results use the explicit `jobs/v1` envelope, including subject,
observation time, freshness, ETag and `has_more`, without a fabricated visibility
role. Gateway failures stop the request. The cost/catalog/auth commands keep
their existing central contracts; they do not test a gateway and fall back.

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

TUI Jobs instead has a Cost mode for its selected job. The existing serialized
reader calls the central detail route with `include_estimate=true`; the response
contains one native observation and its Portal-authorized estimate. The exact
job capability still needs compute authority, with an additional billing scope
check at Center. A cost-only refusal preserves independently readable job facts.
Normal job reads retain their configured direct-site transport. Cost reads are
manual, replace the whole observation and never fall back to the full queue.

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

`runs placement RUN_REF` and the task Location action use the same current
account/site READ selectors. `compute.run-placement/v1` wraps one verified
native execution and the existing `jobs.placement/v1` result. The terminal
reuses its placement parser, display and expiry timer. Expiry removes location
records, retaining only the allocation from that same response. F5 is explicit;
W opens the exact Run with `view=placement`, without carrying metrics or native
identifiers. Site opt-out affects this view; revoked task READ clears Tasks.

`runs stats RUN_REF` uses compute READ and the same account/site selectors.
The serialized TUI reader keeps a separate manual statistics snapshot: F5 replaces
it, and scope/Run/mode changes discard late responses. W adds `view=stats` to the
same Run's console URL, without metrics or file selectors. Source failure clears
statistics; Run READ denial clears Tasks and authentication failure clears all
protected views. See [the statistics contract](../contracts/managed-run-stats/v1/README.md).

`runs cost RUN_REF` is an explicit, independently authorized final-cost read,
requiring `sai.billing.read`. The TUI Cost mode reads one observation manually.
Task-scope revocation clears Tasks; a cost-only refusal clears the amount view
while task metadata remains usable. Its Web continuation adds only `view=cost`
to the exact Run link. File-selection parameters and cost mode are mutually
exclusive. See [the shared cost contract](../contracts/managed-run-cost/v1/README.md).

`runs list`, `runs show RUN_REF`, `runs logs RUN_REF` and `runs files RUN_REF`
require `--workspace-key personal:ID`, `org:ID` or `project:ID` and the configured
or explicit site. Each task remains bound to its recorded account. These commands reject an
explicit `--cluster`; each task's recorded cluster is a returned fact. Run
references come from the task list, not from numeric scheduler IDs.

List/file pages accept `--limit` (1–100) and the previous response's `--cursor`.
Logs accept `--stream stdout|stderr`, `--cursor` and `--max-bytes` (1–65536).
JSON remains the default; table mode displays log control bytes as escaped text.
JSON also escapes terminal control ranges while preserving decoded content.

Tasks in `sai tui` uses its own authorized account-name selection or explicit
`--tasks-workspace-key`. Explicit preselection resolves its name through an exact
`runs workspaces --workspace-key` read, without scanning the directory or
inventing a choice. Tasks operates without
inheriting the Jobs account, storage workspace or Overview's default identity.
The existing worker serializes all reads. Run metadata may refresh; log and
output pages are explicit, one-page observations. Next/Start replace the page;
they do not append an unbounded log. Changing read scope, mode or tab invalidates
late responses. File-read denial clears only the file observation; task-scope
denial clears Tasks, and authentication failure clears all protected views.
Within the same task, changing mode or visiting another tab preserves the last
reading position. Returning rereads the original file, log or evidence through
the same authorized client, then restores its page and scroll position. It does
not reuse a saved body or Web link. Project/task changes and permission loss
clear the corresponding navigation; missing or changed files stop restoration.

### Scheduler jobs

`--scope` accepts `self`, `personal-account`, `org-account`, or
`project-account`.

- `self` rejects account selectors.
- `personal-account`, `org-account`, and `project-account` require exactly one
  of `--account` or `--account-id` under the current Portal contract.
- The CLI maps hyphenated user-facing values to the control-plane underscore
  values. The server remains authoritative.

`--states` is a comma-separated allowlisted token list. `--partition` only
narrows the result.  The running-estimate endpoint deliberately returns the
complete authorized live snapshot and has no client `--limit` parameter.

## Configuration

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
| `SAI_CREDENTIAL_CACHE` | Optional unmanaged path for the protected device refresh cache |
| `SAI_IDENTITY_ISSUER` | SAI Identity OIDC issuer used by `sai auth login` |
| `SAI_OIDC_CLIENT_ID` | Pre-registered public OIDC client identifier |
| `SAI_OIDC_SCOPE` | Reviewed OIDC scopes for the Portal resource (includes `offline_access`) |
| `SAI_OIDC_RESOURCE` | Optional Portal resource/audience identifier |
| `SAI_ALLOW_INSECURE_HTTP` | Development-only explicit HTTP override |
| `SAI_REQUIRE_SITE_CAPABILITY` | Require the server-bound capability/CLI routes; mandatory in managed production wrappers |

## Authentication

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
uses a short-lived browser/device authorization and persists only a rotating,
revocable refresh credential. The CLI must not accept a secret, Bearer token,
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

Cache path precedence is:

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

The device refresh cache defaults to
`${XDG_DATA_HOME}/sai/credentials.json` or
`~/.local/share/sai/credentials.json` and has the same `0700/0600`, symlink,
atomic-replacement, and ownership requirements. A per-user lock serializes
refresh-token rotation across concurrent CLI processes.

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

Running-estimate table output always shows `final=false`, `as_of`, observation
time, age, stale state, and ETag. Times use the response's required site/Slurm
IANA timezone and show an explicit offset, never the center or terminal local
timezone. A pending job has no zero-cost claim; an
unavailable estimate has no guessed amount. Both remain explicit row states.

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

## Legacy wrapper migration

Site-specific legacy commands may later become package-managed wrappers around
the canonical CLI. A wrapper may translate an old command name and select table
format, but it must not query the scheduler directly or implement authorization.

The rollout sequence is: inventory and checksum, stage the new package, canary
through an explicit path, atomically switch package-managed wrappers, validate,
and retain a package-level rollback. This repository does not authorize manual
editing of production command directories.

## Direct output inspection

`runs read` and TUI file inspection consume the same current UTF-8 content DTO as
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
