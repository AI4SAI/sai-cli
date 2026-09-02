# Portal Read API Contract

Status: consumed by the phase-one client

This document records the control-plane contract that `sai-cli` currently
consumes. The control plane remains the source of truth for authorization and
may evolve independently, so contract changes require compatibility tests in
both repositories.

## Authentication

User endpoints require:

```http
Authorization: Bearer <short-lived-token>
```

Unmanaged compatibility bootstrap uses:

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

Managed login-node mode first calls:

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
capability actor. Operations are exact: `jobs.list`, `jobs.detail`, and
`billing.running-estimate` do not imply one another. Missing, expired,
wrong-site, wrong-operation, stale-epoch, or scope/filter-mismatched grants
fail closed. The existing non-CLI routes remain a Portal/Agent contract and
are not a production CLI fallback.

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
