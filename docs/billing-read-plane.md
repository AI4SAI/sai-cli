# SAI Billing / Interactive Read Plane

Status: unified native observation and Portal presentation implementation
candidate; paired production release pending.

This is the cross-product boundary for `sai-cli`, `sai-pilot`, Portal, and site
runtime. Native job facts come from the capability gateway; Portal remains the
only price owner. Network routing may differ by site, but product semantics do
not. Existing production evidence is recorded in the
[basic connection](site-local-read-plane.md#basic-production-connection).

```text
client (CLI/Pilot)
  -> Portal: user session, capability issuance, pricing authority, settled facts
  -> site-read gateway: capability-bound native observations
  -> native Slurm readers
site observations -> Portal operation worker -> exposure/settlement
```

## Ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| `sai-authz` | Ed25519 capability envelope issue/verify | users, policy, key distribution, billing decisions |
| Portal | actor binding, membership, site/account policy, issuer, pricing, settled facts and issuance audit | Identity credentials and native scheduler access |
| Site-read gateway | envelope verification, claim narrowing, native read adapter, short cache, bounded audit buffer | membership/RBAC decisions, wallet/ledger writes, provisioning or scheduler writes |
| Billing contract/kernel | versioned DTOs and deterministic arithmetic used by Portal | independent price policy or final settlement |
| `sai-cli` / `sai-pilot` | explicit intent, bootstrap/renewal, transport, allowlist validation, presentation | Slurm access, price calculation, wallet/ledger access, authorization policy |

The gateway and clients do not calculate prices. Portal applies its existing
start-time pricing and payer visibility rules to the returned observation.
An estimate is always `final=false`; gross and before-credit prices are two
views of the same usage, not amounts to add together or to a settled charge.
Cash, Credit, allowance coverage, exposure and settlement remain Portal-owned.

Interactive reads never create exposure, allowance, wallet, ledger, or payment
rows. Existing billing workers retain observation, exposure and settlement
writes; this candidate adds no collector or business database.

## Capability binding

The outer token is exactly the `sai-authz` v1 envelope. Product fields stay in
the consumer-owned `interactive-read-grant.v1` grant. The only site-read
bindings are:

| Audience | Surface | Exact operations |
| --- | --- | --- |
| `sai-site-read` | `site-read` | `jobs.list`, `jobs.detail`, `jobs.allocation`, `jobs.placement`, `billing.running-estimate` |

Managed CLI issuance uses the existing scope resolver with `entrypoint=cli`
and active shell access; Web/Pilot retain their own entrypoint policy.
The grant binds actor, site, cluster,
compound user/account subject, operation, narrowing partition/state/job filters,
limit maximum, policy epoch, and expiry. A request must be a subset of every
bound filter. The gateway verifies issuer, audience, surface, site, operation,
key/epoch, time window, JTI revocation, and filter narrowing. It does not make
a second membership decision.

The grant shape is unchanged. `billing.running-estimate` retains null `job_id`
and `limit` for the complete authorized queue. Managed costs still require
`sai.billing.read`; job visibility grants no cash-price, wallet or ledger
authority. Portal retains the existing gross/cash distinction: restricted cash
prices stay null with `cash_price_restricted`, without hiding valid job facts.
Managed Run final cost uses its separate
[central contract](portal-api-contract.md#authentication).

The CLI never receives a signing key, shared site-agent secret, or capability
override. It may cache only an opaque capability in a protected user cache.

## Read and billing contracts

Gateway job rows add strict `slurm.job-usage/v1` native facts from the same
observation, with no amount, payer or price revision. Existing CLI job
allowlists ignore that additive field. Portal list/detail/allocation can request
`include_estimate=true`: Center prices each row's observation and attaches its
authorized `running_estimate`, without another native read or a raw Job ID join.
Default job responses keep their existing fields. Missing facts or pricing yield
unavailable amounts and bounded reasons, never zero or a changed job state.

The existing billing APIs and `sai jobs cost` keep `billing.running-estimate/v1`.
Their Center reader consumes `billing.job-observations/v1` from
`GET /v1/site-read/billing/observations` and uses the same estimate owner.
The complete read is bounded by 200,000 rows and 16 MiB, whichever comes first;
truncation or excess size fails closed. A job page is not an account total.
The candidate removes the unused gateway gross-only v2 pricing path, signed
price-bundle configuration and interactive estimate site-agent fallback.

The full queue reader preserves bounded `SETTLING`/`TERMINAL_GAP` retention of
previously observed generations. These are observation gaps, not scheduler
terminal states or settled charges. A disappeared job cannot release exposure
or erase debt. Ordinary Jobs and Managed Runs remain distinct until an
authoritative binding proves their relationship. See the
[native usage contract](portal-api-contract.md#native-usage-and-optional-estimates).

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
fails closed. An ingress proxy, if topology requires one, only forwards transport and
does not authorize, read Slurm, calculate money, or hold a broad secret.

## Delivery gates

1. Keep shared grant/DTO vectors and negative cases in Portal, site runtime,
   and client repositories; reuse existing resolver, adapter, and billing
   arithmetic instead of cloning them.
2. Deliver the Portal issuer, independent gateway verifier/filter/cache, and
   CLI transport as a compatible slice.
3. Pair native-usage observations and Center pricing while preserving billing/v1
   and independent cost permissions.
4. Build clean full-SHA role packages and a tested atomic rollback path.
5. Run a bounded read-only login-node canary for an authorized user; compare queue and
   history before/after and do not submit a job to manufacture a sample.

The Portal candidate presents job state and optional price together; its ledger
view keeps settled entries and the server-owned exposure summary. This slice
does not change CLI/TUI layouts or Pilot tools. Existing real-user empty-list,
issuance/journal and lease-expiry acceptance does not prove this candidate's
paired deployment, positive detail/allocation, revocation or complete task journey.
