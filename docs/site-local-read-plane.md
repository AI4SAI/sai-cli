# Site-Local Interactive Read Plane

Status: target service contract; the shared Portal issuer and the reusable
Slurm interactive adapter are merged, while the independent gateway service is
still a deployment gate.

## Purpose and ownership

Frequent queue/detail refreshes should not perform central policy resolution on
every request. Portal makes the relatively rare authorization decision and the
site gateway reads local native facts under a short-lived capability.

| Component | Owns | Must not own |
| --- | --- | --- |
| Shared contract | capability grant, request, normalized DTO, freshness, bounded error | ORM or native commands |
| Portal issuer | identity/membership/site policy, scope resolution, signing, epoch, audit of issuance | interactive Slurm reads |
| Site-read gateway | signature verification, filter narrowing, native reads, short cache, audit buffer | membership/RBAC, wallet/ledger, provisioning, scheduler writes |
| Native adapter | bounded `squeue` and `scontrol show job` reads | user authorization |
| `sai-cli`/`sai-pilot` | explicit intent, capability renewal, transport, allowlist validation, rendering | keys, policy, Slurm, pricing arithmetic |

The gateway is a separate low-privilege runtime role. It is not the existing
write-capable site-agent process, and it is not packaged in the CLI wheel.

## Capability

The outer token is exactly the `sai-authz` v1 envelope. Product fields are the
typed `interactive-read-grant.v1` payload:

```json
{
  "version": 1,
  "iss": "sai-portal",
  "aud": "sai-site-read",
  "surface": "site-read",
  "site": "site-a",
  "operations": ["jobs.list"],
  "policy_epoch": 7,
  "jti": "opaque-id",
  "nbf": 1785427000,
  "exp": 1785427180,
  "grant": {
    "schema_version": "interactive-read-grant.v1",
    "actor_ref": "opaque-user",
    "cluster_id": "cluster-a",
    "scope_type": "project_account",
    "subject": {"slurm_user": null, "slurm_account": "project-example"},
    "partition": "gpu-standard",
    "states": ["PD", "R"],
    "job_id": null,
    "limit": 100
  }
}
```

Portal derives the exact compound subject through the existing resolver with
`entrypoint=cli` and active shell access. Site-read operations are exact and
independent: `jobs.list`, `jobs.detail`, and `billing.running-estimate`.
Neither job operation grants billing. The gateway verifies issuer, audience,
surface, site, operation, key/epoch, time window, JTI revocation, grant shape,
and request subset before invoking the adapter.

The CLI sends the capability only in `X-SAI-Capability`. It never receives a
signing key, accepts a capability from argv/environment/config, or sends the
Portal Bearer to the gateway.

## Request and response

The gateway request is a `GET` with no authorization query parameters; the
capability carries the authority. The response uses the shared `jobs/v1` or
`billing.running-estimate/v2` DTO documented in
[portal-api-contract.md](portal-api-contract.md). Both include site/cluster,
resolved subject, source freshness, and an ETag. Unknown additive fields may be
ignored only after recursive allowlist validation. Paths, scripts,
environments, raw scheduler data, wallet, ledger, and provider diagnostics are
never returned.

The reusable site runtime adapter has exactly two interactive reads:

- `squeue --json`, with optional user/account/partition/state narrowing and a
  bounded result limit;
- `scontrol show job <ids> --json`, for detail reads.

It has no `sacct`, enforcement, reservation, metadata, provisioning, quota, or
write method. Commands run without sudo, with explicit timeout and output
bounds. A source failure returns a bounded unavailable result; it never falls
back to broad accounting or a guessed empty success.

## Running gross estimate

`billing.running-estimate` is a separate operation. The gateway may reuse the
same scheduler observation and a signed, immutable Portal pricing snapshot, but
it never reads a wallet, allowance table, contract database, or final ledger.
Every result is `final=false`. `estimated` rows contain generation-safe identity,
resource evidence, gross CNY, and a pricing decision revision; `not_started`
and `unavailable` rows carry explicit nulls and bounded uncertainty. A missing
or expired matching snapshot never becomes a guessed amount.

Interactive reads do not create exposure, allowance, wallet, ledger, or payment
rows. A separate transition/checkpoint collector sends idempotent observations
to Portal's operation worker, which independently validates identity and price
revision before persistence and settlement. UI refresh cadence must not drive
that write path.

## Cache and audit

Native source snapshots may be cached briefly. Outward DTO/cache keys include
actor digest, site, surface, operation, scope, normalized filters, policy epoch,
resource/pricing revision, capability digest/JTI, and visibility policy. A key
containing only site or query is invalid. Expired capabilities cannot trigger a
native read; stale local data is display-only and explicitly marked.

The gateway appends bounded audit records and flushes asynchronously. Records
contain reference IDs, actor, site, scope, filters, operation, count, freshness,
and request ID, never capability text, tokens, secrets, scripts, or environment.
Unknown key/epoch, expired/revoked capability, or an over-limit audit backlog
fails closed.

## Network and rollout boundary

A relay may be used for center/satellite topology, but it only forwards the
request and response. It does not authorize, read Slurm, calculate money, or
hold a shared site-agent secret. Both center and satellite use the same gateway
package and contracts; only protected deployment configuration selects the
origin.

The delivery order is: shared vectors and verifier; independent gateway role
and systemd unit; signed pricing/observation contracts; CLI/Pilot compatibility;
development-stack smoke; then an approved GET-only live canary. Local tests and
package builds do not prove a live site or production service.
