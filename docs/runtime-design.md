# Runtime Design

Status: HTTP reads and native job/resource queries; native quota and Portal management planned

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
implements the existing job-helper filter semantics through Slurm JSON; the
[native contract](../contracts/native-jobs/v1/README.md) records names, flags,
units and failure limits. `resources local` reuses the same native execution/value
boundary for one per-node `sinfo` response; its [contract](../contracts/native-resources/v1/README.md)
separates effective capacities, allocations, blocked resources and reported
metrics. Native quota integration follows separately.
Remote errors must not cause a silent source or authority change.

The first management vertical should use an existing account preference action:
discover allowed choices, request a change through the canonical preference
writer, and observe its site-sync result. Check its real OAuth/user authorization
and retry/concurrency contract before exposing it to Agents. Prefer existing
operation receipts; do not add a generic write proxy, task database or approval
framework. JSON operation discovery must distinguish implemented reads, native
prerequisites and management operations rather than advertise planned commands.

## Current implementation

The terminal presentation follows [terminal scope](terminal-scope.md).
With no subcommand, `sai` uses the same central account read: plain text when
stdout is a terminal, JSON when redirected. It returns without prompting and
needs no optional UI package. This changes presentation only; it adds no native
query, site grant or automatic device login. Explicit commands keep their format
defaults and existing argument-order contract.
`sai tui` and `sai status --format tui` share one compact read and return to the
shell. The shared replacement was selected on 2026-10-07; bounded ordinary-user
and SSH/PTY evidence is recorded in the scope decision, separately from human
usability acceptance.

## Command surface

The current release exposes read-only job and resource commands:

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

`sai tui` is the formatted entry to the same `status` command handler. It reads
one authorized account overview, prints it and returns without consuming stdin,
switching terminal screens, polling, opening a browser or starting device login.
No job, file, catalogue or Pilot request accompanies that read. An unavailable
credential directs the user to the existing explicit `sai auth login` flow.

The default uses the applied managed-login account where available; otherwise
Portal resolves its normal overview context. `--account` changes only the read
selector. It does not change a shell directory, submission account or payer.
Both entries accept `--language zh-CN|en-US`. Status keeps JSON as its default;
language changes presentation only. Missing or denied financial facts never
become zero. Rich is optional; JSON and plain table output do not import it.

The full workbench and its job-scope/workspace/partition/state/limit/storage
options are removed. The batch commands retain their own selectors and exact
authority. No deprecated option is silently ignored or widened.

Optional TOML `site_read_base_url` selects direct site reads for `jobs list`,
`jobs show` and `storage native-quota`. `jobs allocation JOB_ID` also requires
this setting and returns the versioned allocation snapshot without a central
fallback. These reads require capability mode and an explicit cluster.
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
