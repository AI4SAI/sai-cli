# SAI Billing / Interactive Read Plane

Status: semantic architecture frozen 2026-09-02; producer, gateway, and
deployment gates remain explicit.

This is the cross-product boundary for `sai-cli`, `sai-pilot`, Portal, and site
runtime. The phase-one production path is the Portal server-bound CLI surface;
the site-local gateway is the next transport using the same capability and DTO
contracts. Network routing may differ between a center and a satellite site,
but product semantics do not.

```text
client (CLI/Pilot)
  -> Portal: user session, capability issuance, pricing authority, settled facts
  -> site-read gateway: capability-bound live facts and gross running estimate
  -> native Slurm readers
site observations -> Portal operation worker -> exposure/settlement
```

## Ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| `sai-authz` | Ed25519 capability envelope issue/verify | users, policy, key distribution, billing decisions |
| Portal | identity, membership, site/account policy, issuer, pricing authority, settled facts, audit persistence, and the phase-one server-bound read surface | site-local cache ownership and native reads in the target gateway path |
| Site-read gateway | envelope verification, claim narrowing, native read adapter, short cache, bounded audit buffer | membership/RBAC decisions, wallet/ledger writes, provisioning or scheduler writes |
| Billing contract/kernel | versioned DTOs and deterministic gross arithmetic | ORM, HTTP, wallet ownership, final settlement |
| `sai-cli` / `sai-pilot` | explicit intent, bootstrap/renewal, transport, allowlist validation, presentation | Slurm access, price calculation, wallet/ledger access, authorization policy |

In the target low-latency path, running facts and estimates come from the
site-read gateway. In phase one, the server-bound Portal surface reuses the
same authorized adapter and returns the same semantics. An estimate is always
`final=false` and is never a charge. Cash, Credit, allowance coverage, and
final settlement remain Portal-owned. The `billing.running-estimate/v1` DTO may
include a bounded before-credit estimate, but never a charge, balance, or
settlement fact.

Interactive reads never create exposure, allowance, wallet, ledger, or payment
rows. A separate site collector sends idempotent observation batches at
transition/checkpoint cadence; that worker owns persistence.

## Capability binding

The outer token is exactly the `sai-authz` v1 envelope. Product fields stay in
the consumer-owned `interactive-read-grant.v1` grant. The only site-read
bindings are:

| Audience | Surface | Exact operations |
| --- | --- | --- |
| `sai-site-read` | `site-read` | `jobs.list`, `jobs.detail`, `billing.running-estimate` |

Portal derives the grant through the existing scope resolver with
`entrypoint=cli` and active shell access. The grant binds actor, site, cluster,
compound user/account subject, operation, narrowing partition/state/job filters,
limit maximum, policy epoch, and expiry. A request must be a subset of every
bound filter. The gateway verifies issuer, audience, surface, site, operation,
key/epoch, time window, JTI revocation, and filter narrowing. It does not make
a second membership decision.

`jobs.list`, `jobs.detail`, and `billing.running-estimate` are separate
operations. Job visibility never implies billing visibility. Settled billing is
a Portal Bearer read with its own future `sai-billing-read`/`billing-read`
contract; it does not use a site-read capability or the Pilot execution token.

The CLI never receives a signing key, shared site-agent secret, or capability
override. It may cache only an opaque capability in a protected user cache.

## Read and billing contracts

`jobs/v1` is an allowlisted normalized job DTO with UTC source time, freshness,
ETag, and no paths, scripts, environments, raw scheduler fields, or billing
data. The phase-one Portal route and CLI consume
`billing.running-estimate/v1`, a non-final DTO with generation-safe job
identity, resource evidence, gross/before-credit decision fields, price
revision, uncertainty, site timezone, freshness, and ETag. The unactivated
gateway candidate remains on its earlier v2 wire shape until its own migration
slice lands. A missing or expired matching price snapshot yields an explicit
unavailable row; no component guesses from the latest price.

The site runtime reuses its canonical Slurm queue/detail adapter. This client
repository owns no native reader and no gateway server. The independent gateway
must be packaged as a low-privilege role separate from the existing
write-capable site-agent package and must exclude `sacct`, enforcement,
provisioning, quota mutation, identity administration, and sudo.

## Cache, audit, and failure rules

Native scheduler snapshots may be cached briefly as an internal source
optimization. Any outward cache key and audit record must include actor digest,
site, surface, operation, scope, normalized filters, policy epoch, pricing or
resource revision, capability digest/JTI, and visibility policy. A site-only key
is invalid. Expired capabilities cannot trigger a native read; stale local data
may be shown only with an explicit stale marker.

The gateway appends a bounded audit record and flushes asynchronously. Records
contain capability/reference IDs, actor, site, scope, filters, operation, count,
freshness, and request ID, never tokens, secrets, scripts, or environments. If
the policy epoch/key is stale or the audit backlog exceeds policy, the gateway
fails closed. A relay, if topology requires one, only forwards transport and
does not authorize, read Slurm, calculate money, or hold a broad secret.

## Delivery gates

1. Keep shared grant/DTO vectors and negative cases in Portal, site runtime,
   and client repositories; reuse existing resolver, adapter, and billing
   arithmetic instead of cloning them.
2. Deliver the Portal issuer, independent gateway verifier/filter/cache, and
   CLI transport as a compatible slice.
3. Add signed pricing snapshot and observation-ingest contracts, then settle
   the Portal-only billing read projection.
4. Build clean full-SHA role packages and a tested atomic rollback path.
5. Run a single GET-only login-node canary for `ordinary-user`; compare queue and
   history before/after and do not submit a job to manufacture a sample.

Local tests and package builds are `local-unit`/`local-static` evidence only.
They do not prove a live gateway, Slurm, Portal deployment, or production
canary.
