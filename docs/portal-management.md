# Portable Portal management

Status: first management action implemented in source; paired production delivery
and ordinary-user acceptance remain unverified.

The same CLI serves a person on a cluster and an Agent on a personal device or
an isolated user VM. Native job, resource and quota queries use the current Unix
identity. Business actions use the user's Identity authorization and Portal's
existing domain services. Neither deployment requires a Pilot session.

## Operation ownership

| User intent | Authoritative owner | CLI responsibility |
| --- | --- | --- |
| Inspect local jobs, resources or quota | Native Slurm/Linux/Lustre | One local observation, human or JSON output |
| Inspect account access, funds or costs | Portal access and billing services | Authorized typed read; preserve estimates versus final facts |
| Choose a default computing identity | Portal preferences and Slurm projection service | Discover allowed choices, submit explicit intent, inspect site receipts |
| Manage membership, budgets, storage or computation | Corresponding Portal domain service | Add one reviewed operation at a time, retaining its role, consent and task rules |
| Read another site's native facts | Selected site's read gateway | Narrow capability and explicit site; no automatic site selection |

There is no generic arbitrary-URL API command, second task store, local business
preference, or Agent orchestration service. JSON discovery must describe only
implemented operations and their actual prerequisites. The terminal summary
does not grow into management pages.

## First complete action: default computing identity

The current setting is global to the user. It selects the existing default
Slurm account and associated login context; sites apply that choice separately.
It does not change already submitted jobs, their payer, the current shell's
directory or an explicitly selected submission account.

The API reuses current membership/site/QOS eligibility and the canonical
preference writer. A machine authentication adapter may have its own route;
it must not copy the browser's business logic. Ordinary Portal account admission
still applies. Shell access is not a substitute for permission to manage a
business preference from a personal device.

- Reads retain `sai.compute.read`. The proposed optional
  `sai.compute.defaults.write` scope permits only changing this default; it
  grants no submission, cancellation, quota, wallet or membership mutation.
  Identity must register and obtain consent for it before production use.
  Existing read sessions and shared login configuration remain unchanged.
- Mutations carry an idempotency key and the caller's expected saved default.
  Portal checks the expectation under the existing principal lock. A replay
  returns the original acceptance without reapplying it after a later change;
  a reused key with another intent or a conflicting current choice is rejected.
  Reuse the existing idempotency table and provisioning generations.
- Acceptance means the central preference and durable site tasks were committed.
  It does not mean the site applied the change. Readback exposes the current
  generation and accepted execution receipt, without raw task payloads or errors.
  A running older generation is still pending for the new choice.
- The global setting must remain coherent across active sites. A choice that
  cannot be projected by the existing service fails the transaction; the CLI
  must not invent a site-specific preference or silently choose another account.
- Network failures never trigger an automatic write retry. An uncertain caller
  can replay the same request key and intent, then read the saved preference and
  site receipt. Receipt time is historical evidence, not continuous monitoring.

## Delivery gates

Verify the ordinary user identity, read-only token rejection, revoked membership,
cross-user isolation, concurrent edits, exact replay and stale site receipt.
Exercise actual HTTP through the installed CLI, then the existing transaction
path on MariaDB. Release the paired Portal/client contract and optional Identity
scope before requesting fresh human consent. Use a standard user for production
acceptance; source tests are not proof of a real site applying the preference.

## Use from a user device or isolated user VM

Select a protected non-secret profile with the existing Portal origin, Identity
issuer, public `sai-cli` client and `sai-portal` resource. Explicitly request
`openid offline_access sai.compute.read sai.compute.defaults.write` for this
management profile, then use `sai auth login` after the operator has registered
the optional scope. A profile change does not itself obtain consent. Keep the
existing read profile/session usable; do not change the shared login-node scope
list merely to enable management on an independent device.

```bash
sai account defaults --site site-a
sai account set-default account-example --if-current auto --request-id request-example-001
sai account defaults --site site-a
```

Use an exact ID from `choices` for the target and the returned
`default_account_id` for `--if-current` (`auto` represents null). The first
response lists choices ready at the selected site, not a promise that another
active site is ready for the same global default. The server validates all
affected projections in the write transaction. To clear an explicit choice,
pass `auto` as the target as well.

`set-default` accepts no explicit site or cluster because it changes the user's
global preference. It needs the central origin and user credential, even when no
site is configured. On an uncertain network result, replay the exact command and
request key; never generate a new key or refresh the expected value for that
replay. Its `accepted` response records the original request, including after a
later edit. Run `account defaults` again to inspect the current setting and
site application. JSON is the default; `--format table` gives a short human view.

Subsequent domain operations follow the ownership table. They do not wait for
3D assets or a Pilot release, and this first action does not claim full Agent
management coverage.
