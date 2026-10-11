# Portal API Contract

Managed task READ accepts explicit personal, organization and project account
keys while retaining the existing DTO versions and field names. The authorized
directory sorts by complete workspace key and validates each cursor in the
current actor/site scope. Task records remain actor-owned; native job visibility
uses its separate account policy. Placement binds the nested scope type to the
Run's account kind while retaining exact user/account and native execution checks.
This client migration requires the paired Center/domain and gateway release;
updating a validator does not activate new account authority or change a payer.

Status: current client contracts, including the deployed unified native-job
observation and central estimate reader.

This document records the control-plane contract that `sai-cli` currently
consumes. The control plane remains the source of truth for authorization and
may evolve independently, so contract changes require compatibility tests in
both repositories.

This is the implemented remote API contract, not the entire CLI product scope.
Local native queries use the caller's Unix/native authority independently.
Default-account management uses the existing domain writer, a separate write
scope and the concurrency/replay contract below. Other Portal management remains
planned. Existing read scopes and capabilities remain read-only. See
[command scope](terminal-scope.md).

## Default computing account

`GET /v1/account/cli/defaults?site_id=...` requires `sai.compute.read` and returns
[`account.defaults/v1`](../contracts/account-defaults/v1/README.md). Choices are
ready at the selected site; the saved preference is global. The current business
default and timestamped site execution receipts remain separate fields.

`PUT /v1/account/cli/defaults` requires `sai.compute.defaults.write`, an
`Idempotency-Key` header and exactly `account_id` and `expected_account_id` in the
body. Both IDs may be null; null clears the explicit preference or compares
against an unset preference respectively. No query selectors are accepted.
The response is [`account.default-change/v1`](../contracts/account-default-change/v1/README.md).
The original acceptance is replayed only for the same actor, key and body.
Current default or request-key conflicts return 409. Scope, account admission,
current membership and existing site projection rules remain server-owned.
No client write retry or authority fallback is allowed.

The paired optional Identity scope and Portal source are prerequisites for this
command. Existing read-only sessions do not acquire it through refresh. See
[portable management](portal-management.md) for consent and delivery boundaries.

## Final job charges

The paired `GET /v1/billing/cli/job-charges` and `/{job_key}` resource reads use
`sai.billing.read` and the existing financial scope resolver, independently of
live queue visibility or shell access. They return
[`billing.job-charges/v1`](../contracts/job-charges/v1/README.md), with exact
amounts from the canonical final fact graph. The list accepts explicit account
scope, site, scheduler-ID narrowing, settlement dates, limit and query-bound
cursor. Exact reads use the record key returned by the list and reject list
filters. There is no capability, native read, pricing or estimate fallback.

`self` is restricted to the actor's charged jobs; account scopes resolve current
financial visibility and preserve funding-field redaction. Same numeric job IDs
may have several accounting incarnations. No default site or native queue grants
access to a historical financial record. These routes require the paired Center
deployment; source compatibility is not production activation.

## Authentication

### Recipient collaboration invitations

`GET /v1/account/cli/invitations` accepts only `limit` (1–100) and the returned
exclusive invitation-ID `cursor`. `GET /v1/account/cli/invitations/{id}` reads
that recipient's invitation and access-task results. Both require
`sai.collaboration.invitations.read`. `POST /v1/account/cli/invitations/{id}/accept`
requires `sai.collaboration.invitations.accept` and an empty JSON object; it
reuses the original acceptance operation. The invitation ID is the natural
replay key. No automatic client retry, site capability, scheduler query or
extra writer is introduced. Unknown/duplicate query fields are rejected.

Paired [page](../contracts/collaboration-invitations/v1/README.md) and
[detail](../contracts/collaboration-invitation/v1/README.md) contracts allowlist
terms and current original task presentations, excluding tokens, contacts,
provider data and raw filesystem paths. The paired API, shared client and optional
Identity scopes are deployed; actual recipient consent and applied access remain
separate. Existing browser invitation routes retain their live consumers.

### Published site discovery

`GET /v1/account/cli/sites` uses the existing Identity `sai.compute.read` scope
and current account admission, without shell access or a selected site. The
[`site.directory/v1`](../contracts/site-directory/v1/README.md) allowlist returns
only published site IDs/names plus page metadata. It reuses the existing Portal
site chooser; this is neither a membership directory nor a routing registry.
Disabled entries are excluded. No SSH address or gateway origin is returned.

`limit` is 1–100 and `cursor` is the previous page's site-ID lower bound. Rows
are sorted by exact ID; deletion/disablement of the cursor row does not broaden
the next page. Later commands explicitly select `--site` and independently
recheck their own authority. Paired source support does not prove deployment.
The [shared delivery record](product-delivery.md#shared-first-use-delivery) records
the subsequent bounded ordinary-user production checks.

### Identity resource tokens

User endpoints require a short-lived access token whose issuer and audience are
validated by Portal. The token is issued by the SAI Identity OIDC provider:

```http
Authorization: Bearer <short-lived-token>
```

The CLI obtains that token with the standard OAuth 2.0 Device Authorization
Grant discovered from the Identity issuer. Identity owns the rotating refresh
token and user session; Portal does not issue a second CLI login credential.
The bounded production device/user-list acceptance is recorded in the
[basic connection](site-local-read-plane.md#basic-production-connection).
It does not establish every operation or subsequent paired release.

The registered CLI read workflow requests `sai.compute.read` for jobs and
`sai.billing.read` for cost estimates, alongside `openid offline_access`.
These are independent OAuth scopes. Neither replaces Portal's exact policy
resolution and operation-bound capability; a jobs-only session cannot read
cost estimates. Scope expansion requires explicit authorization, not an
automatic refresh that silently increases access.

Managed Run final cost has its own explicit Identity-only
`GET /v1/compute/cli/runs/{run_ref}/billing?workspace_key=...&site_id=...`.
It requires `sai.billing.read` and current actor-owned Run/project/site/CLI
admission. The [compute.run-cost/v1 contract](../contracts/managed-run-cost/v1/README.md)
is shared with the console and Pilot. Metadata and file endpoints keep their
existing scopes. Cost access does not extend a Session or enable submission.

Paired Run cost producer: `61e9a5cea214915f4c7506fcf569cf93d236cb43`.
The signed price adjustment preserves a fixed contract price above the current
public price. Other money and quantity fields remain nonnegative.

The former `POST /v1/token` HMAC bootstrap is retired with the Portal issuer.
CLI authentication uses device authorization/refresh or an explicit process-local
Identity `SAI_TOKEN`. Old bearer-cache entries and HMAC configuration cannot
select another credential path. Tokens never enter output or logs.
This authentication retirement has been paired and deployed with Portal/CLI,
as recorded in [CLI authentication](cli-auth.md). Local protocol tests alone
do not establish that deployment or close subsequent acceptance gates.

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
Operations are exact: `jobs.list`, `jobs.detail`, `jobs.allocation`, and
`billing.running-estimate` do not imply one another. Missing, expired,
wrong-site, wrong-operation, stale-epoch, or scope/filter-mismatched grants
fail closed. The existing non-CLI routes remain a Portal/Agent contract and
are not a production CLI fallback.

Account scopes accept exactly one of `workspace_key`, `slurm_account_id` or
`slurm_account_name`. A canonical `personal|org|project:<id>` workspace key must
match `scope_type`; self accepts none of these selectors. Portal's existing
READ resolver maps business ownership to the active native account and repeats
membership, site and channel policy. A workspace ID is not a SlurmAccount ID.
The selector is an issuer/central-request input only: signed grants, gateway
requests and response DTOs retain their existing shapes. Old requests omit it.

The unified observation implementation also routes these central CLI job and cost
reads through the same capability gateway. Center forwards the already verified
capability with explicit narrowing filters, keeps the existing client JSON and
current policy checks, and never falls back to a site-agent reader.

## Job workspace navigation

The retained client navigation contract calls Identity-only
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
An explicit workspace request must also match the returned `workspace_key` exactly.
Source reauthorization after the observation uses the same original selector.

The client constructs a fixed same-origin Jobs link carrying bounded observation
context. `403/job_navigation_workspace_denied` refuses the destination without
revoking an independently valid self observation. Source/identity denials retain
their existing clearing behavior. `503/job_navigation_unavailable` means missing
or ambiguous ownership; it never triggers a default-workspace fallback.

## Resource preparation navigation

The published catalog contract is unchanged. The former TUI preparation action
and its URL helper are removed. The separately owned Web preparation flow reads current
catalog data, then asks the user to choose a currently eligible project through
the existing workspace topology. It does not use task READ discovery as submit
authority, select a project implicitly or derive an account from the partition.

`pilot.resource-selection/v1` carries the preference through the existing Pilot
project/Session/directory chooser. `pilot.resource-draft/v1` then binds it to the
validated native Session in the current tab. Portal's trusted browser action
`resource.inspect` returns one `pilot.resource-inspection/v1` catalog observation
before display/insertion. It does not start/renew a runtime or grant submission.
Deleted/ambiguous resources and changed scopes stop continuation. Concrete
scripts, quantities and prices still require the existing `job_validate`,
`job_render` and proposal confirmation chain.

Paired resource-preparation producer:
`ba29be229d6d9bf970d6dbfcaba035e8dae7c209`.

## My work discovery

`GET /v1/compute/cli/my-runs` and browser `GET /v1/account/compute/my-runs`
return `compute.my-runs/v1`. Normal history accepts `site_id`, `limit` (1–100,
default 50) and `cursor`. A bounded exact `run_refs` filter may narrow the same
read to canonical Run UUIDs, with optional workspace narrowing and no cursor. The authenticated actor is fixed server-side. One
query joins that actor's recorded Runs to currently readable workspaces at the
selected site, including the same redacted names as workspace discovery.

Rows reuse existing Run fields and add `workspace_key`, `workspace_label` and
nullable `organization_label`. Ordering is accepted time descending, then Run
reference descending. A cursor must remain in the current authorized set;
revoked and unrelated anchors fail. No new native query, table, grant or
per-workspace loop is introduced. CLI admission still requires shell access
`enabled`; the browser retains its existing `agent_only` read policy.

See [schema and example](../contracts/managed-my-runs/v1/README.md). The paired
initial producer is `d585187f0`; the deployed paired Center/read-gateway/CLI
versions and bounded acceptance are recorded in [the read-plane delivery](site-local-read-plane.md#replacement-workbench-delivery). Native queue observations,
file access and final costs keep their existing authority; the optional
`run_link` pairs only unique, current native evidence under the
[shared correlation rules](../contracts/managed-run-link/v1/README.md).
It is not an immutable incarnation or authorization proof.

Start work uses the separately owned browser navigation route
`/v1/account/pilot/entry?site_id=...`, optionally with an explicitly applied
workspace key. This is an explicit browser action, not a CLI-authorized API
call. No Identity Bearer or model prompt is placed in the URL. The native entry
producer is merged separately; its paired rollout is required before delivery.

## Managed runs and declared outputs

`GET /v1/compute/cli/workspaces` discovers currently readable task projects at
the explicit `site_id`, requiring the same Identity compute-read and CLI
admission as Run reads. `compute.workspaces/v1` returns safe display labels,
exact workspace keys and bounded keyset pages. See the paired schema and sample
in `contracts/managed-workspaces/v1`. This list does not grant submission,
file, storage or billing access; later requests authorize again. A continuation
whose anchor is no longer readable fails instead of silently changing scope.
Optional `workspace_key` is an exact narrowing filter, mutually exclusive with
`cursor`. Success contains only that choice and no continuation; an inaccessible
key is denied. This resolves explicit terminal preselection without draining
the directory. The response schema is unchanged.
Paired project-discovery and exact-selection producer:
`d0986539e43b795cb4f84ea4efde457c4fe1c400`.

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

An explicitly selected file adds `view=files`, `artifact_ref` and the current
page's request cursor as `artifact_cursor` (omitted for an implicit first page).
The console re-reads only that bounded page and never substitutes another file.
Run/artifact references do not identify sealed content versions. The console's
`GET /v1/account/compute/runs/{run_ref}/pilot-context` rechecks current reads and
the original Pool/Session/mount. It returns no path, ticket or credential.
The task page's explicit Open in Pilot action opens that history without a second
confirmation page. It does not start or renew a model window. Native preview,
prompt insertion and any later execution remain explicit, separately authorized
actions in the paired Web/Pilot clients.

The console and Pilot relay can use separate HTTPS origins. The console carries
one existing Job/Run/resource draft in the bootstrap URL's `sai-context` fragment;
the native receiver consumes it at the destination origin. Portal's authenticated
response owns the approved relay destination. The fragment is not a credential,
does not enter HTTP requests, and never triggers a prompt or model renewal.
This paired browser transport does not change the CLI's fixed console deep link.

Paired result-continuation producer:
`61dfde2fef4f75f9116a755b3ce715ada9a3f11c`.

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
| `workspace_key` | one selector for account scopes | Canonical business scope matching `scope_type`; server resolves native ownership |
| `slurm_account_id` | one selector for account scopes | Native compute account ID, distinct from the workspace owner ID |
| `slurm_account_name` | one selector for account scopes | Account name; mutually exclusive with the other selectors |
| `partition` | no | Narrowing filter |
| `states` | no | Comma-separated narrowing filter |
| `limit` | no | Integer from 1 through 500, default 100 |
| `source_preference` | no | Currently fixed to `live` |
| `include_estimate` | no | Portal opt-in: literal `true` or `false`, default false |

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

The default job response must not expose:

- work directories, stdout/stderr paths, submit scripts, commands, or
  environment variables;
- raw scheduler or site-agent payloads;
- wallet, balance, pricing, ledger, payment, or refund fields;
- credentials, internal secrets, or raw provider errors.

### Native usage and optional estimates

Deployed paired implementation: gateway `jobs/v1`
items and `jobs.allocation/v2.job` add `native_usage` from the same native row:

```json
{
  "schema_version": "slurm.job-usage/v1",
  "database_index": "12345",
  "alloc_tres": {"cpu": 8, "gpu": 1, "nodes": 1, "mem_mb": "16384"},
  "unavailable_reason": null
}
```

`database_index` is a positive decimal string or null. Allocation is the strict
typed object above or null; its absence or invalid input carries
`missing_allocation`, `invalid_allocation` or `invalid_job_identity` as applicable.
This is native metering evidence, not a price or a financial permission.
Existing CLI job allowlists ignore this additive field.

Portal `/v1/slurm/jobs`, detail and allocation accept explicit
`include_estimate=true`. Center applies its existing pricing and payer-visibility
policy to that row's observation and adds `running_estimate` using the item
contract below. It strips native usage from its ordinary job response; false or
absent opt-in preserves the old fields. Placement does not accept the option.
The paired CLI detail route `/v1/slurm/cli/jobs/{job_id}` also accepts this
option. It retains `sai.compute.read`, current CLI policy and the exact
`jobs.detail` capability, then independently requires `sai.billing.read` when
the option is true. Missing billing scope returns `job_cost_read_denied` without
a native read; ordinary job reads remain available. This does not add an option
to the CLI list route, change a grant, or put prices in the site gateway.

`sai jobs cost JOB_ID` uses this existing central detail-cost request even when ordinary
jobs use a direct site origin. It reads one job with an exact grant, without
list pagination or a partition filter. Explicit state filters only narrow the
read; without one, state changes remain visible. The attached item is validated
against its parent job. CLI cost JSON also preserves `has_more=false` and the validated freshness
`observed_at`, `ttl_seconds`, `age_seconds`, `stale` fields alongside `queried_at`.
This additive serialization keeps machine consumers from guessing freshness.
The whole observation
is returned as one response; neither another list nor a local price join is
used. Unsupported producers fail explicitly, with no fallback to a broad read.
The command keeps the allowlisted job envelope and its attached
`running_estimate` in JSON. The detail contract has UTC timestamps and no site
timezone field; its human output therefore uses UTC rather than guessing a site
or local timezone. Omitting the ID preserves the full-scope cost contract.
The paired Center and shared-client installation completed on 2026-10-02.
Ordinary-user historical task reads passed through that installed client.
On 2026-10-07, shared source `5bfe8f74c690` added the batch entry and passed a
positive current-job read under an ordinary user's authorized organization
scope. Candidate and selected JSON/table reads matched the original job,
account and execution times; the exact native source was `scontrol`. The backend
and shared connection configuration were unchanged. This proves consumption of
one non-final estimate, not independent pricing or final settlement correctness.

Paired CLI detail-cost producer: `905f6601026eccea8051e7db0b29e407c2386852`.

Each attached estimate binds the full array-task ID, user/account and exact UTC
submission/start times of its parent row. No browser-side job-ID join is allowed.
Missing native usage yields unavailable amounts and `native_usage_unavailable`;
cash restrictions retain the existing partial/gross semantics. Price errors do
not alter scheduler state. A page estimate never claims a complete account total.

Native elapsed time follows Slurm's active-runtime semantics, including suspension,
at the same source observation time. Paused time is not priced as active runtime.
The existing queue-retention path freezes the last observed duration instead of
extending it when a job leaves the queue. Explicit zero elapsed stays zero and
does not become a wall-clock estimate or a claim of free final billing.

## Running job cost estimates

```text
GET /v1/billing/running-estimates
```

This independent billing-visibility endpoint accepts the same scope and
narrowing filters as the job list endpoint, except that it has no `limit`
parameter: it prices the complete authorized live snapshot. The implementation's
optional per-job attachment above does not replace this complete-scope contract.
`source_preference` remains fixed to `live`.

The Center reader uses gateway
`GET /v1/site-read/billing/observations` with the existing independent billing
capability and unchanged null job/limit grant. `billing.job-observations/v1`
contains site/cluster/scope/subject, site timezone, freshness, ETag,
`has_more=false` and job rows with native usage. The complete response must fit
both 200,000 rows and 16 MiB; truncation fails closed. Center alone calculates
prices, and the external billing/v1 API and CLI `sai.billing.read` checks remain.
This replaces the interactive estimate site-agent reader without a fallback.

The response contract is `billing.running-estimate/v1`. Top-level fields are
`operation`, `version`, `schema_version`, `site_id`, `site_timezone`,
`cluster_id`, `scope`, `visibility_role`, `activity_visibility`, `slurm_user`, `slurm_account`,
`as_of`, `freshness`, `etag`, `items`, `summary`, `count`, and `final`. `operation` is `billing.running-estimate`,
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

## Settled billing

`jobs charges` uses the independent [final charge contract](#final-job-charges)
and current Portal financial authorization. It reads the existing validated
final fact graph; it does not acquire a site capability, reuse the generic
ledger response, expose wallet internals or calculate prices. `jobs cost`
continues to describe a non-final running estimate. Paired production delivery
of the final-charge reader is recorded separately in the roadmap.

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
The same Identity credential lifecycle applies to development clients.

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
authentication always retain their documented central routes. The observation
implementation removes the unused gateway billing v2 price response; no direct-site
cost transport is added to the client. Consumers must opt into jobs/v1 and
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

Paired Portal producer: `ecb4f96e56820ac86b6f19e0a8128f289727810c`.
The placement schema/sample are byte-identical across Portal, CLI and Pilot.

## Storage quota summary

`GET /v1/account/cli/storage/workspaces` returns the independent
[`storage.workspaces/v1` directory](../contracts/storage-workspaces/v1/README.md).
It requires Identity `sai.storage.read` and enabled-shell CLI admission, reuses
the storage quota reader's current membership predicates, and lists only scopes
with active access at the explicit site. It takes `site_id`, `limit` (1–100),
and optional `cursor` or exact `workspace_key`; the last two are mutually
exclusive. Exact success contains one matching choice, never an unrelated or
empty successful resolution. Revoked pagination anchors fail explicitly.
Names and opaque keys are the only per-item facts. No quota reader, full Web
topology, capability issuer or native probe is invoked. Every later quota read
authorizes independently and retains its source-specific behavior.

Paired storage-directory producer: `d0986539e43b795cb4f84ea4efde457c4fe1c400`.

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

## Managed Run node registration

`GET /v1/compute/cli/runs/{run_ref}/placement` accepts `workspace_key`/`site_id`
with compute scope and current actor-owned project/Run READ. Browser and Pilot
use the same service through their existing authenticated entrypoints. The
server derives native selectors and the correlation marker, and relays only a
narrow signed capability to the configured site-read gateway. It never returns
that capability or a site-agent credential to this command.

The [shared Run placement contract](../contracts/managed-run-placement/v1/README.md)
uses a strict `interactive-run-read-grant.v1` inside the existing signed envelope;
ordinary job grants remain separate. Old gateway code rejects it, and an ordinary
placement response cannot satisfy the Run wrapper. No fallback removes the
binding. Gateway-before-center paired rollout is required; source tests are not
deployment proof. No scheduler reference is 409, uncertain submission/source is
503, and site opt-out is 403 `run_placement_not_enabled`, independent of Run READ.

## Native managed Run statistics

`GET /v1/compute/cli/runs/{run_ref}/stats` accepts only `workspace_key` and
`site_id`, with `sai.compute.read` and current actor-owned Run/project/site/CLI
admission. The browser uses `/v1/account/compute/runs/{run_ref}/stats`; Pilot
uses its existing Session read identity and internal `run.stats` operation.
The shared [compute.run-stats/v1 contract](../contracts/managed-run-stats/v1/README.md)
returns step-specific CPU/RSS observations, nullable native facts and query window.
Read permission is independent of file ACL, payer eligibility and model renewal.
CLI never receives the dedicated site-agent credential or chooses the native user,
job, account or correlation marker. Runtime SLUID plus before/after allocation
and step metadata protect the observation's execution binding. No history fallback,
GPU metric or per-node utilization is synthesized. The initial native parser is
fixed to Slurm 26.05.1 / data_parser v0.0.45; other versions are unavailable.

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

## Managed output content

`GET /v1/compute/cli/runs/{run_ref}/artifacts/{artifact_ref}/content` uses the
existing Identity resource scope and shell policy. The corresponding browser
route under `/v1/account/compute/runs` supports its existing read policy.
`workspace_key` and `site_id` are required; optional `artifact_cursor` is the
selected output-list request page, and `cursor` is the previous content response's
version-bound byte cursor. No filename or native path is accepted from the client.

The response is the allowlisted [content contract](../contracts/managed-run-content/v1/README.md).
Run and applied file READ are independently rechecked for every section. A changed
file is not appended to old contents. `artifact.read` exposes the same DTO through
the existing independent internal Agent read service; native Pilot tool registration
and production release are separate, and this change grants no execution rights.

## Complete managed output download

`POST /v1/compute/cli/runs/{run_ref}/artifacts/{artifact_ref}/download` reuses
current Identity authorization and Run/file READ. Its exact JSON request is
`{workspace_key, site_id, artifact_cursor, version}`; the last two fields may be
null. A renewal sends the original version. A version change fails the transfer.

The `compute.run-artifact-download/v1` grant binds `workspace_key`, `site_id`,
`run_ref` and `artifact_ref`, and includes `download_name` (basename only),
`size_bytes` (integer, at most `2^53-1`), a 64-lowercase-hex `version`,
`download_url`, opaque `capability` (at most 16 KiB), integer Unix-second
`expires_at` and `transfer_until`, and `range_max_bytes=8388608`.
Capability lifetime is at most 300 seconds and the transfer window at most one
hour; the client permits at most 60 seconds of positive clock skew on these
upper bounds, while rejecting an already expired grant.
Only HTTPS or loopback HTTP and the exact `/v1/site-files/artifacts/download`
path are accepted; credentials, queries, fragments and redirects are forbidden.

The direct GET sends `X-SAI-Capability` and `If-Match: "<version>"`, with one
`Range: bytes=start-end` of at most 8 MiB. It never sends Identity Bearer or login
cookies. Each nonempty response must be `206` with exact `Content-Range`,
`Content-Length` and ETag. An empty file instead uses GET without Range and
requires `200`, zero length and the same ETag. Encoded/chunked or mismatching
responses fail closed. A `401` permits one fresh grant for that range; `403`,
changed files and other failures do not trigger broad retries.

Neither grant nor binary contents are printed. A completed local save returns
`compute.run-artifact-saved/v1` with the request bindings, explicit local output
path, size and version. Download capability material is never persisted.

## Organization job scope

Organization reads include the root and currently authorized project accounts.
Portal resolves active ownership, member windows, site access and per-project
activity visibility once. It signs `interactive-read-grant.v2` when child
accounts are present. `subject.subaccounts` contains sorted exact
`{slurm_account, slurm_user}` intersections, not a gateway expansion instruction.
The gateway matches each job against one intersection before pagination.

Expanded responses use jobs/v2, jobs.allocation/v3, jobs.placement/v2 and
billing.job-observations/v2; central jobs use jobs.portal/v2 with subaccounts
and central estimates use billing.running-estimate/v2. Exact scopes retain the
preceding DTOs. Organization-to-project navigation returns jobs.web-context/v2
with the original scope in source_context and the reauthorized project as
the target. Old clients cannot be assumed to understand these responses.

One grant contains at most 64 accounts, including the root. Oversized scopes
return site_read_scope_too_large and require selecting a project. Direct signed
leases keep the existing short-expiry/revocation contract; central relays
recheck current complete scopes. Final billing, managed Runs and storage keep
their existing domain permissions.
