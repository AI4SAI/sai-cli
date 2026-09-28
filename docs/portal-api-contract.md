# Portal Read API Contract

Status: consumed by the phase-one client

This document records the control-plane contract that `sai-cli` currently
consumes. The control plane remains the source of truth for authorization and
may evolve independently, so contract changes require compatibility tests in
both repositories.

## Authentication

User endpoints require a short-lived access token whose issuer and audience are
validated by Portal. In the target architecture the token is issued by the
SAI Identity OIDC provider:

```http
Authorization: Bearer <short-lived-token>
```

The CLI obtains that token with the standard OAuth 2.0 Device Authorization
Grant discovered from the Identity issuer. Identity owns the rotating refresh
token and user session; Portal does not issue a second CLI login credential.
The Identity provider/device endpoint is a separate cross-repository release
gate and is not yet a production fact in this repository.

The registered CLI read workflow requests `sai.compute.read` for jobs and
`sai.billing.read` for cost estimates, alongside `openid offline_access`.
These are independent OAuth scopes. Neither replaces Portal's exact policy
resolution and operation-bound capability; a jobs-only session cannot read
cost estimates. Scope expansion requires explicit authorization, not an
automatic refresh that silently increases access.

The pre-Identity compatibility bootstrap currently retained by Portal uses:

```text
POST /v1/token?username=...&ts=...&nonce=...&key_id=...&sig=...
```

Successful bootstrap response:

```json
{
  "token": "redacted",
  "expires_at": 1785427200,
  "can_access_portal": true,
  "can_access_mis": false
}
```

The CLI never prints or logs `token` or `sig`.

### Server-bound CLI capability

Managed login-node mode requires an Identity-issued resource token and first calls:

```text
POST /v1/authz/site-read
```

with the user Bearer and the exact requested operation/site/cluster/scope and
narrowing filters. Portal resolves the same scope with `entrypoint=cli`, which
requires `LinuxShellAccess.ENABLED`, then returns
`sai-site-read-capability/v1`. The opaque capability is sent in
`X-SAI-Capability` to:

```text
GET /v1/slurm/cli/jobs
GET /v1/slurm/cli/jobs/{job_id}
GET /v1/billing/cli/running-estimates
```

The server requires the original user Bearer as well and binds it to the
capability actor. The issuer and all three CLI read routes reject legacy
Portal-issued credentials; there is no CLI authentication downgrade switch.
Development compatibility credentials remain limited to the non-CLI endpoints.
Operations are exact: `jobs.list`, `jobs.detail`, `jobs.allocation`, and
`billing.running-estimate` do not imply one another. Missing, expired,
wrong-site, wrong-operation, stale-epoch, or scope/filter-mismatched grants
fail closed. The existing non-CLI routes remain a Portal/Agent contract and
are not a production CLI fallback.

## Job workspace navigation

The TUI's explicit Open Web action calls Identity-only
`GET /v1/slurm/cli/jobs/{job_id}/web-context` with the original site, cluster,
scope and exact account selector plus `source_preference=live`. It sends the
Portal Bearer only, with no capability or direct-site request from the client.
Portal reuses its capability-only relay for one current allocation observation,
then resolves the native runtime account to its unique current workspace owner.
Both source read and destination membership/site/user-account visibility are
checked; compute-submit and payer authority are not navigation prerequisites.

The shared `jobs.web-context/v1` schema/sample are in
`contracts/job-web-context/v1`. The ten allowlisted fields identify the workspace,
site, cluster, destination account scope/ID, canonical job ID and observation/
submission/restart evidence. The server returns no arbitrary URL or credential.
Original account scopes remain bound to the same account; self can resolve to
any currently authorized account kind. Unknown added response fields are dropped.

The client constructs a fixed same-origin Jobs link carrying bounded observation
context. `403/job_navigation_workspace_denied` refuses the destination without
revoking an independently valid self observation. Source/identity denials retain
their existing clearing behavior. `503/job_navigation_unavailable` means missing
or ambiguous ownership; it never triggers a default-workspace fallback.

## Managed runs and declared outputs

`GET /v1/compute/cli/workspaces` discovers currently readable task projects at
the explicit `site_id`, requiring the same Identity compute-read and CLI
admission as Run reads. `compute.workspaces/v1` returns safe display labels,
exact workspace keys and bounded keyset pages. See the paired schema and sample
in `contracts/managed-workspaces/v1`. This list does not grant submission,
file, storage or billing access; later requests authorize again. A continuation
whose anchor is no longer readable fails instead of silently changing scope.
Paired project-discovery producer: `adac8bf51990b15b6aef3dfa14d055fcb0e6b408`.

Identity-only central routes consume `sai.compute.read` and current CLI access:

```text
GET /v1/compute/cli/runs
GET /v1/compute/cli/runs/{run_ref}
GET /v1/compute/cli/runs/{run_ref}/logs
GET /v1/compute/cli/runs/{run_ref}/artifacts
```

Every route requires the explicit `workspace_key` and `site_id`. The list is
owner-only and uses descending accepted time plus run reference, with a scoped
last-row reference as its next cursor. A cursor from another actor/workspace/site
cannot broaden the query. State/detail expose allowlisted `compute.runs/v1` and
`compute.run/v1` receipts; final charges, worker internals and correlation IDs
are excluded. Current project READ can inspect an owned run without submission,
active payer, writable files or a current Pilot activation.

Logs and artifact metadata reuse `compute-run-log.v1` and
`compute-run-artifacts.v1`, adding explicit workspace/site response binding.
Each call separately requires the current applied READ permission for the
frozen directory. `run_file_read_denied` does not imply that task state became
inaccessible. Logs preserve the stream-bound byte cursor, UTF-8 byte count,
availability and completion; unavailable is not an empty completed log. Files
are the current declared outputs, including exact size/nanosecond metadata and
relative display names, not a content-addressed archive or download grant.

The four paired schemas and examples are in `contracts/managed-runs/v1`.
Paired Portal producer: `159d81291965d105147c4d4c1b1ad9d075db14f3`.
This identifies source compatibility, not a deployed server version.
Unknown extra fields are dropped. File content is a specifically authorized
log field; it never enables arbitrary file paths or native command output in
errors. No client-side pricing, new task record or polling daemon is added.

The console reuses these four DTOs under browser-authenticated
`/v1/account/compute/runs` and the corresponding run/logs/artifacts paths.
The route fixes `entrypoint=portal_read`, allowing the existing `agent_only`
read policy while CLI routes still require shell access `enabled`. The caller
cannot choose the entrypoint. Both surfaces resolve current account, project,
site and owner-only Run visibility, with file READ checked separately.
The task deep link is a fixed same-origin workspace `runs?run_ref=...` route.
It is an object selector, not a credential, Pilot admission or file-content grant.

## List jobs

```text
GET /v1/slurm/jobs
```

Supported query parameters:

| Parameter | Required | Contract |
| --- | --- | --- |
| `site_id` | yes | Site token |
| `cluster_id` | no | Optional cluster token |
| `scope_type` | yes | `self`, `personal_account`, `org_account`, or `project_account` |
| `slurm_account_id` | account scopes | Exactly one account ID or name is required for every account scope |
| `slurm_account_name` | account scopes | Exactly one account name or ID is required; server authorizes it |
| `partition` | no | Narrowing filter |
| `states` | no | Comma-separated narrowing filter |
| `limit` | no | Integer from 1 through 500, default 100 |
| `source_preference` | no | Currently fixed to `live` |

The client does not send raw `user`, arbitrary query parameters, or a
non-live source preference.

The current route calls Portal's `portal_read` policy entrypoint. It rejects
`LinuxShellAccess.DISABLED` but permits `AGENT_ONLY`. This is valid for Portal
or Agent read-only surfaces, but it is not the final login-node CLI contract.
A dedicated endpoint or surface-bound capability/token must enforce
`LinuxShellAccess.ENABLED` before production CLI wrappers are enabled.

## Show one job

```text
GET /v1/slurm/jobs/{job_id}
```

It accepts the same site, cluster, scope, account, states, and source fields as
the list endpoint. It does not accept partition or limit. A `404` means the job
does not exist or is not visible; the client must not distinguish those cases.

## Response

Both endpoints return the same envelope. The detail endpoint returns one item.

```json
{
  "site_id": "site-a",
  "cluster_id": "cluster-a",
  "scope": "project_account",
  "visibility_role": "read",
  "slurm_user": null,
  "slurm_account": "project-example",
  "items": [
    {
      "job_id": "12345",
      "array_task_id": null,
      "name": "simulation",
      "slurm_user": "alice",
      "slurm_account": "project-example",
      "state": "R",
      "state_label": "running",
      "priority": 1000,
      "submit_time": "2026-07-31T00:00:00Z",
      "start_time": "2026-07-31T00:01:00Z",
      "elapsed_seconds": 3600,
      "run_wait_seconds": 3600,
      "partition": "gpu-standard",
      "qos": "normal",
      "nodes": 1,
      "slots": 8,
      "gpus_per_node": 1,
      "mem_per_unit": "16G",
      "reason_or_nodelist": "compute-node"
    }
  ],
  "count": 1,
  "freshness": {
    "source": "squeue",
    "queried_at": "2026-07-31T01:01:00Z"
  }
}
```

Every item must contain exactly the documented semantic field set after client
normalization. Values may be null where the scheduler has no fact. Unknown
server fields are not forwarded by the CLI.

The response must not expose:

- work directories, stdout/stderr paths, submit scripts, commands, or
  environment variables;
- raw scheduler or site-agent payloads;
- wallet, balance, pricing, ledger, payment, or refund fields;
- credentials, internal secrets, or raw provider errors.

## Running job cost estimates

```text
GET /v1/billing/running-estimates
```

This independent billing-visibility endpoint accepts the same scope and
narrowing filters as the job list endpoint, except that it has no `limit`
parameter: it prices the complete authorized live snapshot. It is not a
pricing option on `/v1/slurm/jobs`. `source_preference` remains fixed to
`live`.

The response contract is `billing.running-estimate/v1`. Top-level fields are
`operation`, `version`, `schema_version`, `site_id`, `site_timezone`,
`cluster_id`, `scope`, `visibility_role`, `slurm_user`, `slurm_account`,
`as_of`, `freshness`, `etag`, `items`, `count`, and `final`. `operation` is `billing.running-estimate`,
`version` is `v1`, `schema_version` is `billing.running-estimate/v1`, and `final` is always
`false`.

Freshness contains `source`, `observed_at`, non-negative `ttl_seconds` and
`age_seconds`, and native-boolean `stale`. ETag is a body field for the source
snapshot; it is not an HTTP response-header contract.

Each item contains only:

```json
{
  "job_key": "opaque-generation-key",
  "job_id_raw": "12345",
  "slurm_job_db_index": null,
  "slurm_user": "alice",
  "slurm_account": "project-example",
  "state": "RUNNING",
  "submit_time": "2026-08-14T00:00:00Z",
  "start_time": "2026-08-14T00:01:00Z",
  "elapsed_seconds": 3600,
  "resources": {
    "partition": "gpu-standard",
    "qos": "normal",
    "nodes": 1,
    "alloc_tres": {
      "gpu": 1,
      "cpu": 8,
      "mem_mb": "16384",
      "billing": null,
      "nodes": 1
    },
    "resource_type": "gpu",
    "resource_count": 1,
    "usage_quantity": "1.00000000"
  },
  "gross_cny": "2.00000000",
  "cash_before_credit_cny": "1.80000000",
  "currency": "CNY",
  "price_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "estimate_status": "estimated",
  "uncertainty": [],
  "final": false
}
```

`estimate_status` is `estimated`, `partial`, `not_started`, or `unavailable`.
`cash_before_credit_cny` is the contract or activity cash-price estimate before
SAI Credit, allowances, reservations, or other coverage. It is neither an
expected deduction nor a promise of the final Credit/cash split. An `estimated`
item has non-null gross and before-credit amounts, price revision, resource
type, resource count, and usage quantity, with empty `uncertainty`. A `partial`
item has the same gross price and resource facts, a null before-credit amount,
and non-empty machine-code `uncertainty`.
`PENDING` and `CONFIGURING` jobs use `not_started`: `resource_type`,
`resource_count`, `usage_quantity`, both amounts, and `price_revision` are
null, although observed allocation evidence may remain. An unavailable job
uses null amounts and bounded machine-code `uncertainty`; the response does
not fail as a whole. Money is an unsigned CNY decimal string with exactly eight
fraction digits. `site_timezone` is the job site's required IANA Slurm timezone.
Non-null `price_revision` is a 64-character lowercase SHA-256 hash over the
normalized gross and before-credit pricing decision. A partial estimate hashes
the stable unavailable cash decision and reason code, never a raw error or
transient diagnostic.
Non-null `submit_time` and `start_time` values, like `as_of` and
`freshness.observed_at`, are normalized UTC timestamps ending in `Z`; table
output converts them with `site_timezone` and displays the resulting offset.

The CLI validates this response recursively as an allowlist and ignores
additive unknown fields. It does not cache responses, inspect wallets or
ledgers, call Slurm, or calculate any amount.

## Settled billing (future independent contract)

Settled job cost is deliberately not part of the site-read capability or the
current CLI command surface. A future `billing.settled.read` Portal Bearer
route must query only `JobBillingSettlement.status=succeeded` rows with a
complete `SlurmJobBillingFact`/ledger/line-item/usage graph, apply the same
scope and site/cluster authorization, and return a new allowlisted DTO. It
must not reuse `/v1/billing/ledger`, expose wallet/ledger internals, or let the
client recompute a final amount. The command name, pagination, and DTO version
remain open until that Portal contract is frozen with compatibility tests.

## Bounded errors

The control plane may return a string `detail` or an object containing a short
`code` and user-safe `message`. The CLI maps HTTP status and bounded error code
to its stable exit categories. It does not echo arbitrary nested bodies.

Expected examples include source unavailable, source contract invalid,
authentication failure, authorization denial, unsupported query, and job not
found or not visible.

## Change discipline

- Additive response fields are allowed; older clients ignore them.
- Removing or changing a documented field requires a versioned migration.
- Adding a query parameter does not permit the CLI to send it until the client
  contract is reviewed.
- A local fake server test does not establish live scheduler compatibility.

## Self account status

The separate `GET /v1/account/cli/overview` is the normal-authority login/workbench
read, documented in [account.overview/v1](../contracts/account-overview/v1/README.md).
It takes site and an optional authorized applied account, uses `sai.compute.read`
and enabled shell access, and exposes finance only with `sai.billing.read` and
the existing workspace financial visibility. It does not inherit the recovery
route's wider availability or require a native site capability.

Managed `sai auth status` calls `GET /v1/account/cli/status` with its existing
Identity resource Bearer. The route accepts no user, workspace or site selector,
requires the current subject binding, and remains readable for identity recovery.
It does not grant job access or require a site-read capability.

The `account.status/v1` DTO contains `verification_current`, `access_state`,
`initial_verification_deadline` (UTC ISO 8601 or null), and `verification_url`.
The only accepted URL is `/portal/#/portal/account/identity-assurance`, resolved
against the configured API origin. The CLI never accepts an arbitrary redirect,
recalculates deadlines, queries identity databases, or emits credential material.
Development bootstrap credentials retain their previous local-only status.

## Published site resource catalog

`sai resources catalog` reads `site.resource-catalog/v1`. Managed mode calls
`GET /v1/account/cli/sites/{site_id}/resource-catalog` with an Identity resource
Bearer (`sai.compute.read`). Portal resolves the current subject and requires
shell access `enabled`. The unmanaged development route is
`GET /v1/account/sites/{site_id}/resource-catalog`, the same route used by WebUI.
Neither route reads live scheduler state or grants site access; published
catalog visibility is independent from permission to submit or access files.

There are no query parameters, account selectors or cluster selectors. The
site's published runtime configuration selects its canonical catalog. Unknown
or disabled sites fail; a source failure is unavailable, not an empty catalog.
The managed route does not accept legacy Portal tokens or require a site-read
capability. Token cache refresh follows the existing one-retry policy.

The recursive allowlist contains `schema_version`, `site_id`, `site_label`,
`compute` and `storage`. Exact fields, limits and a synthetic example are in
[the shared contract](../contracts/site-resource-catalog/v1/README.md).
Nullable specifications must be explicit nulls. Prices are server-provided
non-negative decimal strings in CNY with their own unit; no client conversion,
discount, entitlement or final-charge claim is made. `gpu_count` is the
published total GPU count, unlike the per-node GPU column in the jobs table.

Narrative text preserves ordinary tab/newline whitespace in JSON; the table
folds it to spaces. Terminal control bytes, invalid types, unsupported versions
and a different response site are rejected. Unknown additive fields are
discarded at every modeled level. Pilot receives the identical catalog under
`published_catalog`, alongside its existing scheduler preparation metadata.

Deploy the matching Portal producer before upgraded CLI/WebUI/Pilot consumers.
Schema/sample parity and fake HTTP prove local compatibility, not production
availability. This catalog does not implement hardware topology or utilization.

## Direct site job reads

Optional `site_read_base_url` in the existing TOML profile selects a fixed
trusted gateway origin for `jobs list/show`. It requires
`require_site_capability=true` and an explicit `cluster_id`. The address must
be an HTTPS origin without a path, query, fragment or user information.
Unmanaged local tests may use loopback HTTP; the broad insecure-development
switch cannot enable a non-loopback HTTP gateway. There is no argv or
`SAI_SITE_READ_BASE_URL` override, and Portal responses cannot change the origin.

```toml
[profiles.default]
base_url = "https://portal.example.org"
site_id = "site-a"
cluster_id = "cluster-a"
require_site_capability = true
site_read_base_url = "https://read.example.org"
```

The client requests the existing exact `jobs.list` or `jobs.detail` capability
from Portal, then sends a GET to `/v1/site-read/jobs` or
`/v1/site-read/jobs/{job_id}`. Only `X-SAI-Capability` reaches the gateway;
Identity Bearer credentials never do. No query parameters are necessary:
the capability already binds all filters. Capability cache keys include the
selected read origin. A gateway 401 for a cached capability may renew that
capability once through Portal; a newly issued capability failure, 403, timeout
or source failure does not trigger a fallback or an Identity login refresh.
The issuer's own expired cached Bearer handling remains a bounded retry.

This is an explicit response-contract choice, not an invisible transport swap.
Direct mode returns the gateway's versioned `jobs/v1` envelope:

- `schema_version`, `site_id`, `cluster_id`, `scope_type`;
- `subject` containing nullable `slurm_user` and `slurm_account`;
- `freshness` containing source `squeue|scontrol`, UTC `observed_at`, integer
  `ttl_seconds` and `age_seconds`, and boolean `stale`;
- a SHA-256 `etag`, boolean `has_more`, and typed `items`, including the
  established job fields and `state_label`.

It has no `visibility_role` or `count`: the grant binds a subject rather than a
Portal membership label, and a bounded page is not a total count. The client
validates the version, exact site/cluster/scope, any explicit account name,
per-item subject, filters, limit and requested detail ID. Unknown fields are
ignored recursively; unsafe text or inconsistent freshness is a contract error.
Known long/short scheduler state aliases compare equivalently without changing
the signed request. `has_more` reports authorized results beyond this limit;
no pagination cursor or complete-history claim is made.

The default gateway now reads native queue/detail on demand under the signed
filters. It filters the bounded response again before limiting it, normalizes
native timestamps to UTC, hashes only authorized output, and does not invent
terminal states for vanished jobs. The adapter has a timeout and rejects
oversized captured output; the current process runner does not impose a
streaming memory ceiling. Production load and concurrency require separate
validation. Explicit test/integration cache injection is not the default path.

Without this setting, existing Portal job JSON is unchanged. Cost, catalog and
authentication always retain their documented central routes; the gateway's
older billing v2 candidate is not enabled. Consumers must opt into jobs/v1 and
deploy the matching gateway producer first. Local subprocess and HTTP tests do
not prove a live scheduler, installed gateway or production wrapper rollout.

### Job allocation snapshots

The shared producer/consumer contract is `contracts/job-allocation/v2/README.md`.
The v2 migration must pair the gateway, Portal relay, CLI and Pilot consumers.
It replaces v1 without interpreting an older response as complete v2 evidence.
Paired Portal producer: `3cf695ad8e9c6fe8f05fe00ed72d1f81e4dbf782`.

`sai jobs allocation JOB_ID` requires the explicit gateway configuration above;
without it the command fails before making any request. It requests the exact
`jobs.allocation` capability with the same grant constraints as `jobs.detail`,
then calls `GET /v1/site-read/jobs/{job_id}/allocation` through the same transport
and bounded capability renewal. No central job endpoint is an alternative.

The `jobs.allocation/v2` response carries the same `site_id`, `cluster_id`,
`scope_type`, `subject`, `freshness` and SHA-256 `etag` as `jobs/v1`, with
`freshness.source=scontrol`. It replaces `items` and `has_more` with:

- `job`: the same 19 allowlisted job fields. `job_id` is the numeric base ID;
  `array_task_id` is a separate numeric string or null. The combined ID must
  match the requested job exactly. A base job never substitutes for its task.
- `scheduler_states`: 1–32 strings matching `[A-Z][A-Z0-9_]{0,31}`, preserving
  base state and transition flags; the first state must agree with `job.state`
  after the established long/short normalization. The CLI does not infer allocation from a
  short job state or discard flags such as `COMPLETING`.
- `restart_count`: integer 0–65535 or null, from the observed native counter.
  This is not a persistent attempt identifier; no attempt ID is invented.
- `allocation`: `status` and `nodes`. `allocated` has 1–4096 unique nodes;
  `not_allocated` has `[]`; `unavailable` has null. Each node contains only
  `name` (`[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`), nonnegative integer `cpus`,
  nonnegative integer or null `memory_mib`, and nullable `gres`.
  Zero CPU counts remain zero. GRES entries contain `name`, nullable `type`,
  exact nonnegative int64 `count` and nullable sorted unique int32 `indices`.
  Per node there are at most 32 entries, unique by name/type; per entry at most
  4096 indices, with length equal to count. Whole observations allow at most
  4096 entries and 65,536 indices. An unavailable layer is null, not zero.

The producer binds `gres_detail` to the same job's native node index and ordered
hostnames expansion before sorting output. IDX observations provide Slurm-local
indices; CNT and shared MPS/shard observations provide quantities only. Counts
retain the named GRES units. No original GRES text, per-slot shared capacity,
UUID, CUDA index, MIG parent or physical slot leaves this projection.

Missing or transitional native allocation facts may be unavailable. Null is
never translated to zero or an empty allocation. This is a snapshot allocation,
not physical inventory, GPU utilization, a permanent job attempt, or an aggregate
of heterogeneous job components. The CLI only validates and displays the
producer's facts. Unknown fields are discarded at every level. JSON remains the
default; `--format table` identifies allocated resources and observation freshness,
with `-` for unavailable numeric values.

## Registered job placement

`sai jobs placement JOB_ID` uses the same exact-job selector and explicitly
configured site origin as allocation. Its Portal `/v1/authz/site-read` request
requires the independent `jobs.placement` operation and existing compute-read
scope. Portal additionally requires `site_read_placement_enabled=true` for that
site. An allocation capability cannot read placement; read access does not add
administrator, submission, filesystem or billing authority.

The capability-only `GET /v1/site-read/jobs/{job_id}/placement` carries no
caller-selected nodes or racks. The [shared contract](../contracts/job-placement/v1/README.md)
embeds one complete `jobs.allocation/v2` and inventory provenance. Placement
rows match its allocated node names/order exactly. Each is recorded, unmapped
or expired; only recorded rows carry safe asset/incarnation references, optional
rack/U position, verification time and validity deadline. Nonallocated or
unavailable allocation needs no inventory and returns empty placement rows.
Unknown fields are removed recursively and invalid bindings/times fail closed.

WebUI uses Portal's `/v1/slurm/jobs/{job_id}/placement` relay with its current
entrypoint policy. Pilot obtains a fresh Session-bound read capability through
`/v1/internal/pilot/read/job-placement-capability`. All three surfaces share
the DTO, while preserving their entrypoint authorization. This is operator
registration, not proof of current physical incarnation, utilization, full
rack occupancy or a stable execution identity. Local fixtures are not site
asset verification or deployment acceptance.

## Storage quota summary

`GET /v1/account/cli/storage/quota-summary` uses only `workspace_key` and
`site_id`. Keys are explicit `personal:<id>`, `org:<id>` or `project:<id>`;
Slurm account selection never implies storage workspace selection. Extra or
repeated query keys are rejected. `sai storage quota-summary` supports the
usual connection option ordering; an explicit cluster selector is rejected.

This Identity-only route requires `sai.storage.read`, a linked active subject
and shell access enabled. The existing Portal quota service resolves current
membership and site access. It does not require job submission permission,
start a runtime, read paths, request site-agent credentials or query Lustre.
No legacy-token fallback exists, regardless of the jobs transport setting.

The [storage.quota-summary/v1 contract](../contracts/storage-quota-summary/v1/README.md)
contains scope/mount references, delivery state, target/effective capacity,
nullable sampled usage and remaining capacity, observed block/inode limits,
and separate observation/quota-update times. Decimal values remain server
strings in TiB. Negative remaining capacity is valid; null is not zero.
Unknown additive fields are discarded; missing modeled fields, wrong scope,
invalid values or timestamps fail closed. `source=portal_quota_observation`
always identifies stored facts, even after the user presses Refresh.

`ready` means quota delivery is ready; it is not a live-source guarantee.
`pending`, `failed`, `drift` and `unavailable` remain data states, not a successful
quota change. Lack of site access produces the same `unavailable`/null summary
as the existing WebUI; a source error is an HTTP failure with no partial output.
Paths, administration actions, subscription details and final money are excluded.

Deployment requires the separate optional storage scope in the Identity client
registration, the matching Portal producer, and explicit device reauthorization
when adding the scope to managed configuration. Updating the CLI package does
not overwrite managed configuration or grant a new scope to cached sessions.
The registered scope remains subject to Portal authorization on every read.

## Native storage quota

`storage native-quota` requires a trusted `site_read_base_url`. The CLI sends
only `workspace_key` and `site_id` to `POST /v1/authz/storage-read` with the
Identity resource Bearer and `sai.storage.read`; Portal requires active shell
access and resolves current workspace/site visibility plus typed project-ID
assignments. Read permission is independent of submission and quota enforcement.
The response is `sai-storage-read-capability/v1`, with the existing capability,
expiry, audience/surface fields and exact operation/site/workspace echoes.

The subsequent `GET /v1/site-read/storage/native-quota` has no query parameters
and only `X-SAI-Capability`. The site checks its protected mount/namespace mapping
and actual Lustre filesystem source before an unprivileged `lfs quota -p` query.
It checks the returned project subject and strictly parses native counters.
Neither credentials nor paths or raw project IDs appear in the public result.

The [shared DTO](../contracts/storage-native-quota/v1/README.md) is
`storage.native-quota/v1`, with `source=lustre_quota` and
`coverage=authorized_quota_subjects`. Each row has exact decimal-string byte
and inode counters, native soft/hard limits, safe references/label and UTC
query completion time. Native zero limits mean unlimited. Per-row times may
differ; this is not an atomic filesystem snapshot or a full organization pool
total. Shared directories do not gain a separate quota or permission to see
the organization's root. Sponsored-home funding is not aggregated here.

At most 64 subjects and a 16 KiB capability are supported; an oversized scope
fails explicitly, without truncation. There is no pagination or historical-data
claim. Source failure, inaccurate native values and expired capabilities never
fall back to stored summary data. Data responses are not cached; capability
renewal uses the existing bounded policy and includes the trusted read origin
in its cache key. Unknown additive response fields are discarded recursively.

This issuer is CLI-specific. WebUI/Pilot require their own entrypoint policy
before consuming the same native DTO; this route does not expand Agent grants.
Installation and a read as the actual gateway service UID on the actual Lustre
client remain separate deployment/acceptance gates.
