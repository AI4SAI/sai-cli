# Site-Local Interactive Read Plane

Status: job list/detail and native Lustre quota transport/gateway code are
implemented locally; production installation and readback remain separate
gates. Billing and future resource operations retain their own gates.

## Purpose and ownership

Frequent queue/detail refreshes should not perform central policy resolution on
every request. Portal makes the relatively rare authorization decision and the
site gateway reads local native facts under a short-lived capability.

Dynamic facts default to on-demand native reads at the site. The gateway
normalizes those reads; it is not a replicated scheduler or storage database.
Coalesce concurrent identical reads and use brief, explicitly timestamped
reuse where the source cost warrants it. A new UI does not require a central
telemetry store or an always-running full-inventory collector.

Slurm queue/detail adapters already provide this native-read foundation. A
future resource-state operation must extend the reviewed
operation contract and reuse the native source/parser, without importing the
write-capable storage adapter's administrative authority. A native quota query
is distinct from a recursive directory scan; the latter does not belong in
the synchronous interactive path.

The separate `storage quota-summary` command reads existing Portal observations
and delivery state. It is a central business read, explicitly labeled by source
and observation time; it does not enable a native storage operation in this
gateway or replace the on-demand design.

ComputeRun intents, idempotency, execution receipts, membership and settlement
remain durable control-plane facts. Current native observations do not replace
those records, and a client refresh cannot advance their state. Historical
sampling is added only for a named feature with a bounded retention policy.

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

Managed-task project discovery stays at Portal. It reuses current membership
and site read policy, returns a bounded name/selector page and neither queries
the native site nor issues another capability.

Managed-run logs and declared output-file listings retain their existing
ComputeRun readback path through Portal and its dedicated `interactive-read`
site credential. The CLI holds only its Identity token and sends no file path,
username or site secret. Portal checks current file READ and frozen mount
lineage before calling the two bounded site methods. Those methods reject
redirects and responses above 1 MiB; the log content itself is at most 64 KiB
and an output page at most 100 files. This does not create a file capability in
the native jobs/quota gateway or a second filesystem reader.

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
independent: `jobs.list`, `jobs.detail`, `jobs.allocation`, and `billing.running-estimate`.
No job operation grants billing. Allocation uses the same exact job grant
constraints as detail. The gateway verifies issuer, audience,
surface, site, operation, key/epoch, time window, JTI revocation, grant shape,
and request subset before invoking the adapter.

The CLI sends the capability only in `X-SAI-Capability`. It never receives a
signing key, accepts a capability from argv/environment/config, or sends the
Portal Bearer to the gateway.

The client opts in using a trusted TOML `site_read_base_url` origin. Job
list/detail, allocation and explicit native quota use it; catalog, stored quota
summary, authentication and running cost remain central.
The read origin participates in the capability cache key. No failed gateway
read falls back to another source.

## Request and response

The gateway request is a `GET` with no authorization query parameters; the
capability carries the authority. The phase-one Portal CLI route uses the
`billing.running-estimate/v1` DTO. The existing unactivated gateway candidate
still emits its earlier `billing.running-estimate/v2` shape and must be migrated
to the frozen v1 contract before that transport is enabled. Direct jobs use the
explicit gateway `jobs/v1` envelope documented in
[portal-api-contract.md](portal-api-contract.md#direct-site-job-reads), while the
default Portal job envelope remains unchanged. Direct jobs include site/cluster,
resolved subject, source freshness, truncation and an ETag; no Portal membership
role is inferred. Unknown additive fields may be
ignored only after recursive allowlist validation. Paths, scripts,
environments, raw scheduler data, wallet, ledger, and provider diagnostics are
never returned.

The reusable site runtime adapter supports these bounded native reads:

- `squeue --json`, with optional user/account/partition/state narrowing and a
  bounded result limit;
- `scontrol show job <ids> --json`, for detail and allocation snapshots;
- `scontrol show hostnames <expression>`, only to expand an observed allocation's
  host expression. This does not query all-node state or physical inventory.

The paired `jobs.allocation/v2` projection also reads `gres_detail` from that
same job response. Slurm JSON already enables detail. Index-to-node binding
uses the native ordered expansion before sorting; it adds no node-state query.
Unknown GRES remains null independently of valid CPU/memory observations.

It has no `sacct`, enforcement, reservation, metadata, provisioning, quota, or
write method. Commands run without sudo, with explicit timeout and output
bounds. A source failure returns a bounded unavailable result; it never falls
back to broad accounting or a guessed empty success.

## Native Lustre quota

The independent `storage.quota.read` operation uses `storage-read-grant.v1`;
it does not add storage subjects to the Slurm grant. Portal binds each current
typed project-ID assignment to its filesystem namespace and mount, using the
existing workspace/site and directory visibility policy. The gateway shares
the original signature, epoch, revocation and expiry verifier.

Its protected mount mapping supplies a readable quota anchor and exact expected
native filesystem source. The gateway checks `findmnt`, then executes only
`lfs quota -p` for authorized subjects. It has no sudo or write adapter. Its
pure parser is shared with the existing storage readback implementation, without
shipping storage administration code in the gateway package.

The [native quota DTO](../contracts/storage-native-quota/v1/README.md) separates
subject observations from business pool totals and stored delivery state. A
failed, partial or inaccurate native query returns an error, never old data.
Commands have a deadline and a captured-output limit; the runner still has no
streaming memory ceiling. Protected binding configuration and service-UID access
must be verified on the real site before enabling this optional operation.

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

The implemented default job path reads on demand with native subject/filter
arguments and then filters again before limiting. It does not reuse the
billing collector's cluster-wide cache or synthesize terminal states. Short
reuse/coalescing is a future measured optimization, not a new required service.
The ETag describes only authorized normalized output and truncation; unrelated
job changes cannot alter it.

Before production, the gateway must append bounded audit records and flush
asynchronously. This remains a rollout gate, not proof supplied by the direct
transport tests. Records
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
