# Site-Local Interactive Read Plane

Status: target architecture, not implemented by the phase-one CLI

## Motivation

A terminal UI can refresh job lists and details every few seconds. At a remote
site, sending every refresh to a central authorization service adds network
latency and concentrates load. The target design separates a relatively rare
authorization decision from frequent site-local fact reads.

The control plane still owns identity, membership, site access, policy, and
billing visibility. It issues a short-lived, narrow, site-bound capability.
A site-local gateway verifies that capability and reads native scheduler or
storage facts without performing per-request central introspection.

## Components

| Component | Owns | Must not own |
| --- | --- | --- |
| Shared contract | Capability, query, response, freshness, bounded error, and audit schemas | ORM or native reader code |
| Control-plane issuer | Scope resolution, policy epoch, capability signing, snapshot publication, audit ingestion | Interactive native reads |
| Site-local gateway | Signature verification, claim narrowing, short cache, request coalescing, DTO redaction, audit buffer | Membership decisions or write operations |
| Native adapters | Bounded reads from scheduler, filesystem, topology, and health sources | User-facing authorization |
| `sai-cli` | Capability bootstrap/renewal and local requests | Signature keys, policy logic, or raw broad access |

## Capability shape

A future capability should be asymmetric-signed and contain at least:

```json
{
  "iss": "sai-control-plane",
  "sub": "user:opaque-id",
  "aud": "site-read-gateway:site-a",
  "site_id": "site-a",
  "surface": "cli",
  "scope_type": "project_account",
  "slurm_user": null,
  "slurm_account": "project-example",
  "allowed_operations": ["jobs.list", "jobs.detail"],
  "filters": {
    "partitions": ["gpu-standard"],
    "states": ["R", "PD"]
  },
  "limits": {"jobs.limit": 500},
  "visibility": {"show_slurm_user": true, "show_workdir": false},
  "policy_epoch": "policy-v1",
  "jti": "opaque-capability-id",
  "nbf": 1785427000,
  "exp": 1785427180
}
```

Rules:

- `allowed_operations` is an allowlist, not an advisory label.
- A request may only take a subset of every filter and a lower limit.
- Audience, site, time window, key ID, policy epoch, and revocation state are
  checked locally.
- The CLI never receives a signing key or a broad site-agent secret.
- A capability is bearer-like and must be cached with the same care as a token.
- Job visibility and billing visibility are separate grants. A capability that
  allows `jobs.list` or `jobs.detail` does not implicitly allow a running-cost
  estimate.

## Query and response

The shared request shape should be independent of the native reader:

```json
{
  "operation": "jobs.list",
  "site_id": "site-a",
  "filters": {"states": ["R"], "partition": "gpu-standard"},
  "limit": 100,
  "cursor": null,
  "if_none_match": null,
  "freshness_preference": "cache_then_live"
}
```

The response carries source and consistency explicitly:

```json
{
  "ok": true,
  "operation": "jobs.list",
  "items": [],
  "next_cursor": null,
  "etag": "opaque-etag",
  "freshness": {
    "source": "scheduler_live",
    "observed_at": "2026-07-31T01:00:00Z",
    "queried_at": "2026-07-31T01:00:01Z",
    "ttl_seconds": 5,
    "stale": false,
    "confidence": "observed"
  },
  "partial": false,
  "errors": [],
  "audit_ref": "opaque-audit-reference"
}
```

Bounded error codes include capability expiry or scope mismatch, stale policy,
source unavailable or timeout, invalid contract, stale cache, and unavailable
rate data. Raw native stderr and provider payloads are never part of this
contract.

## Native-first read domains

The gateway is a thin read facade, not a replacement resource system.

| Domain | Native source class | Typical TTL | Forbidden by default |
| --- | --- | --- | --- |
| Jobs | Scheduler queue and job-detail JSON | 2-15 seconds | Script, environment, paths, raw JSON |
| Resources | Scheduler node/partition state plus signed catalog | 5-60 seconds | Hidden-job identity and raw admin diagnostics |
| Placement | Scheduler allocation plus cgroup/GPU/topology facts | 2-10 seconds | Other users' process details |
| Storage | Runtime snapshots, mount state, and quota readback | 30-300 seconds | Credentials and broad filesystem walks |
| Usage estimate | Scheduler resource evidence plus signed pricing snapshot | 2-10 seconds | Wallet and final ledger data |
| Identity health | Local identity projection health | 30-300 seconds | Keytabs, credential caches, and admin secrets |

The gateway must not replicate an accounting database, build a second quota
index, or maintain a strong-consistency topology database. One slow source
returns partial or unavailable; it does not trigger a broad fallback chain.

## Running usage estimate contract

A running estimate is a separate operation, such as
`billing.running-estimate`, with its own billing-visibility claim and response
allowlist. It is not an additive field set on `jobs.list`. The control plane
resolves the payer, workspace, site, membership window, billing visibility,
and applicable signed pricing revision before issuing the capability.

The site gateway may reuse the same scheduler observation that serves the job
list. It applies the signed pricing snapshot without reading a wallet,
contract database, allowance table, or final ledger. The Portal endpoint and
batch CLI now consume the frozen `billing.running-estimate/v1` DTO documented
in [portal-api-contract.md](portal-api-contract.md). A future site-local
capability transport must preserve that exact DTO, including the required site
IANA timezone, UTC source timestamps, freshness, ETag, uncertainty, and
`final=false` fields.

Invariants:

- Every result is explicitly `final=false`; user-facing clients label it as an
  estimate, never a charge or settled cost.
- Usage is billable allocated/dominant-resource usage, not GPU or CPU
  utilization. Optional performance telemetry cannot change the estimate under
  the current pricing contract.
- The price revision hashes normalized gross and before-credit pricing
  decisions. A partial result hashes a stable unavailable decision and bounded
  reason code, never raw errors, transient diagnostics, or wallet identifiers.
- Without an allowance hold, the gateway cannot promise the final split among
  SAI Credit and cash for concurrently running jobs.
- A live key includes `JobIDRaw`, user/account, and submit/start generation so
  Job ID reuse, arrays, and heterogeneous components cannot collide. The final
  identity is the control-plane `(site_id, slurm_job_db_index)` settlement key;
  the site collector must establish a unique, auditable mapping.
- When a job leaves `squeue` before final `sacct` data is visible, the last
  estimate remains in a bounded terminal-grace state. It is not silently
  dropped or added to the final amount.
- Final control-plane settlement uses its own canonical DBIndex and never
  waits for this live mapping, telemetry, or an exposure row. The client
  replaces the estimate only after mapping succeeds; otherwise it keeps an
  explicitly bounded terminal-gap state for reconciliation and never adds the
  estimate to the final amount.
- Refreshing the gateway cannot create ledger, allowance-usage, funding, or
  wallet records.
- A stale estimate may be displayed only with explicit freshness. It cannot by
  itself authorize job cancellation or another write action.

The CLI, a future TUI, the Portal relay, and a future site-local low-latency Web
view consume the same DTO. The local Web view is a read-only presentation
client, not a second Portal; it owns no account, wallet, membership, or write
workflow.

Interactive reads and risk persistence are separate chains. A user request
only reads the 2-15 second in-memory cache and never creates or updates a cash
exposure. Independently, the site collector sends site-scoped, idempotent
batches of job identity, allocation, state, observation time, and source
revision to the control plane. The control plane resolves payer and pricing
and writes the canonical ACR exposure snapshot.

The persistence cadence is change-driven for start, allocation, identity, and
terminal transitions, plus a lower-frequency checkpoint/heartbeat (target
default 300 seconds, configurable down to 60 seconds near a risk threshold).
It must not mirror the UI refresh cadence. Batches update only materially
changed, new-bucket, or near-expiry jobs, so an idle UI and a heavily refreshed
UI produce the same database writes.

The first server implementation belongs to the existing site-runtime package:
it reuses that package's Slurm read adapter and normalized DTO behind a
separate low-privilege unit, runtime identity, and role-scoped package
manifest. This repository owns the client transport and compatibility
fixtures, not a second native `squeue` reader or a gateway server inside the
CLI wheel.

## Cache isolation

Cache keys include actor digest, site, surface, operation, scope, workspace,
normalized filters, policy epoch, catalog version, pricing snapshot, capability
digest, and visibility policy. A cache keyed only by site and filter can leak
data across actors.

Cached DTOs are not authorization. Each live request must still present a
valid capability. Once a capability expires, a client may display explicitly
stale local data but cannot initiate another native read.

## Audit and failure behavior

The gateway appends a bounded audit record locally and flushes asynchronously.
Audit records contain capability/reference IDs, actor, site, scope, filters,
operation, result count, source freshness, and request ID. They do not contain
the capability itself, tokens, secrets, scripts, or environment variables.

If the control plane is unreachable while a capability remains valid, the
gateway may serve authorized reads until expiry and mark central reachability.
If the capability is expired, the policy epoch is stale, the key is unknown,
or audit backlog exceeds site policy, the gateway fails closed.

## Delivery phases

1. Freeze versioned JSON schemas and negative test vectors.
2. Implement a fake issuer and verifier with audience, filter, expiry, epoch,
   key rotation, and revocation tests.
3. Add cross-repository fixtures for the site-runtime gateway's shared
   observation cache, cache isolation, request coalescing, ETag, and bounded
   errors; do not implement a second native reader here.
4. Freeze an independent billing capability and running-estimate DTO with the
   Portal, including estimate-to-final replacement vectors.
5. Freeze the separate site-telemetry batch contract and prove interactive
   reads cause zero exposure writes.
6. Add the client transport behind the existing command interface.
7. Validate the site-runtime role manifest proving the gateway contains no
   write authority and that no gateway server enters the CLI wheel.
8. Run a development-stack protocol test.
9. Run a separately approved, read-only live canary.

No earlier phase may be reported as proof of a later one.
