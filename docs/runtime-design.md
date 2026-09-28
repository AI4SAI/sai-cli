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

`jobs placement` requires the explicit site gateway and an independent
`jobs.placement` capability. It returns the same response's allocation and
operator-recorded registration for only those nodes. Site opt-in is required;
there is no inventory fallback. TUI registration inspection pauses polling and
clears expired metadata independently of its refresh interval, without sending
another request. Ordinary allocation inspection remains available separately.

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

`runs list`, `runs show RUN_REF`, `runs logs RUN_REF` and `runs files RUN_REF`
require `--workspace-key project:ID` and the configured or explicit site. The
current producer owns project-backed ComputeRuns. These commands reject an
explicit `--cluster`; each task's recorded cluster is a returned fact. Run
references come from the task list, not from numeric scheduler IDs.

List/file pages accept `--limit` (1–100) and the previous response's `--cursor`.
Logs accept `--stream stdout|stderr`, `--cursor` and `--max-bytes` (1–65536).
JSON remains the default; table mode displays log control bytes as escaped text.
JSON also escapes terminal control ranges while preserving decoded content.

Tasks in `sai tui` uses its own authorized project-name selection or explicit
`--tasks-workspace-key`, without
inheriting the Jobs account, storage workspace or Overview's default identity.
The existing worker serializes all reads. Run metadata may refresh; log and
output pages are explicit, one-page observations. Next/Start replace the page;
they do not append an unbounded log. Changing project, mode or tab invalidates
late responses. File-read denial clears only the file observation; task-scope
denial clears Tasks, and authentication failure clears all protected views.

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
username = "alice"
key_id = "managed-login"
timeout_seconds = 10
```

Tokens and shared secrets are rejected in the TOML file. They must be supplied
through a short-lived environment or a managed node credential mechanism.

Relevant environment variables:

| Variable | Purpose |
| --- | --- |
| `SAI_API_BASE_URL` | Control-plane base URL |
| `SAI_SITE_ID` | Default site |
| `SAI_PROFILE` | Profile name |
| `SAI_API_USERNAME` | Actor username for unmanaged compatibility token exchange |
| `SAI_API_KEY_ID` | Client key identifier for unmanaged compatibility exchange |
| `SAI_TOKEN` | Already-issued short-lived Bearer token |
| `SAI_API_SHARED_SECRET` | Protected HMAC secret for unmanaged compatibility exchange |
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

1. use `SAI_TOKEN` for the current process without writing it to disk;
2. reuse a valid CLI device access token;
3. rotate a valid SAI Identity OIDC refresh credential at the discovered
   `token_endpoint`;
4. reuse a legacy protected cache entry;
5. for an unmanaged compatibility client, exchange a HMAC request at
   `POST /v1/token` and cache only the returned short-lived Bearer token.
   Managed login nodes never carry the HMAC secret; they use SAI Identity's
   OAuth 2.0 Device Authorization Grant after a one-time browser approval.

The HMAC canonical string is part of the existing Portal compatibility
contract:

```text
username + "\n" + unix_timestamp + "\n" + nonce + "\n" + key_id
```

The compatibility secret is not a general login mechanism. `sai auth login`
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
- entries keyed by normalized base URL, username, and key ID;
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
