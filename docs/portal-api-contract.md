# SAI Read-Plane Contract

Status: frozen for the site-read client; Portal and gateway producers remain
separate deployment gates.

This document is the wire contract consumed by `sai-cli`. Portal remains the
authority for identity, membership, site/account access, policy, and settled
billing. The CLI never queries Slurm, a Portal database, a wallet, or a broad
site-agent endpoint.

## User authentication

An already-issued user session is sent to Portal as:

```http
Authorization: Bearer <short-lived-token>
```

An unmanaged compatibility client may obtain that session through the existing
HMAC bootstrap:

```text
POST /v1/token?username=...&ts=...&nonce=...&key_id=...&sig=...
```

The CLI never prints or logs the token, signature, or shared secret. Managed
login-node mode does not use the HMAC secret; it accepts only a protected,
short-lived `SAI_TOKEN` injection.

## Site-read capability issuance

The client sends one exact JSON object to Portal:

```text
POST /v1/authz/site-read
Authorization: Bearer <short-lived-token>
Content-Type: application/json
```

```json
{
  "operation": "jobs.list",
  "site_id": "site-a",
  "cluster_id": "cluster-a",
  "scope_type": "self",
  "slurm_account_id": null,
  "slurm_account_name": null,
  "partition": null,
  "states": ["PD", "R"],
  "job_id": null,
  "limit": 100
}
```

`operation` is exactly one of `jobs.list`, `jobs.detail`, or
`billing.running-estimate`. `self` requires no account selector; every account
scope requires exactly one account name or ID. `jobs.list` requires `limit` and
rejects `job_id`; `jobs.detail` requires `job_id` and rejects `partition` and
`limit`; running estimates reject both. States are sorted, unique, and bounded.
Portal repeats all validation and resolves the exact user/account intersection
with `entrypoint=cli`, including active shell access.

The response is an opaque capability envelope and a bounded echo:

```json
{
  "schema_version": "sai-site-read-capability/v1",
  "capability": "opaque",
  "expires_at": 1785427180,
  "audience": "sai-site-read",
  "surface": "site-read",
  "operation": "jobs.list",
  "site_id": "site-a",
  "cluster_id": "cluster-a"
}
```

The capability is the fixed `sai-authz` v1 envelope with an
`interactive-read-grant.v1` grant. It is sent only as `X-SAI-Capability` to the
independent gateway. The Portal Bearer is never sent to that gateway. A grant
binds actor, site, cluster, exact compound subject, operation, narrowing
filters, limit maximum, policy epoch, and expiry. The gateway rejects wrong
audience/surface/site/operation, unknown key or stale epoch, expiry, revoked
JTI, malformed grant, and any request that widens a bound filter.

The legacy Portal job and running-estimate routes remain separate Portal/Agent
contracts. They are not a fallback for managed CLI mode, and this client does
not expose their direct query parameters.

## Jobs response: `jobs/v1`

The gateway returns one normalized object:

```json
{
  "schema_version": "jobs/v1",
  "site_id": "site-a",
  "cluster_id": "cluster-a",
  "scope_type": "self",
  "subject": {"slurm_user": "alice", "slurm_account": null},
  "freshness": {
    "source": "squeue",
    "observed_at": "2026-07-31T01:01:00Z",
    "ttl_seconds": 5,
    "age_seconds": 1,
    "stale": false
  },
  "etag": "opaque-snapshot-etag",
  "has_more": false,
  "items": []
}
```

Each item contains exactly these normalized fields:

```json
{
  "job_id": "12345",
  "array_task_id": null,
  "name": "simulation",
  "slurm_user": "alice",
  "slurm_account": "project-example",
  "state": "R",
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
```

The client ignores additive unknown fields after recursive validation and
never forwards paths, scripts, commands, environments, raw scheduler payloads,
wallet/ledger data, credentials, or provider errors. Every returned item must
remain inside the response subject's non-null user and account filters.

## Running estimate response: `billing.running-estimate/v2`

Running estimates are independent site-read results, always `final=false`, and
never a charge. The top-level object contains:

```text
schema_version, site_id, cluster_id, scope_type, subject, site_timezone,
freshness, etag, final, items
```

`site_timezone` is a valid IANA zone. `freshness` uses UTC `observed_at` and
bounded non-negative TTL/age values. Each item contains:

```json
{
  "job_generation_key": "opaque-generation-key",
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
    "alloc_tres": {"gpu": 1, "cpu": 8, "mem_mb": "16384", "nodes": 1},
    "resource_type": "gpu",
    "resource_count": 1,
    "usage_quantity": "1.00000000"
  },
  "gross_cny": "2.00000000",
  "currency": "CNY",
  "pricing_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "estimate_status": "estimated",
  "uncertainty": []
}
```

`job_generation_key` is required for every row so Slurm ID reuse and arrays do
not collide. `estimated` requires a start/elapsed fact, gross amount,
pricing revision, resource type/count/usage, and empty uncertainty.
`not_started` has no pricing/resource usage fields and empty uncertainty.
`unavailable` has null gross/pricing and at least one bounded machine-code
uncertainty; observed resource facts may remain. Money is an unsigned CNY
decimal with exactly eight fractional digits, and `pricing_revision` is a
lowercase SHA-256 decision digest. No cash/Credit/allowance, wallet, ledger,
payment, or settlement field is part of this contract.

The client does not cache this DTO, read a price table, or calculate an amount.
Table output converts UTC timestamps to the returned site timezone and labels
every value as a non-final estimate.

## Errors and evolution

The server may return a bounded code/message or a string detail. The client
maps status to its stable exit categories and never echoes nested JSON, HTML,
native stderr, private paths, addresses, or secrets. Missing/expired/wrong-site
capabilities and source failures fail closed; no broader query or accounting
fallback is attempted.

Additive response fields are ignored until modeled. Removing or changing a
modeled field requires a coordinated versioned migration and compatibility
fixtures in Portal, site runtime, and this repository. Local fake-server tests
prove request/response mapping only; they do not prove a live gateway,
scheduler, or production deployment.
