# Portable Portal management

Status: the first management action's Center, shared CLI and optional Identity
scope are deployed. On 2026-10-11 an independent Linux client completed an
ordinary user's approved account change and restoration, with new site receipts
and native readback for both. Exact replay, stale-value rejection, isolated-grant
revocation and preservation of the daily read-only session also passed. Broader
management domains and platform coverage remain separate work.

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

- Reads retain `sai.compute.read`. The optional
  `sai.compute.defaults.write` scope permits only changing this default; it
  grants no submission, cancellation, quota, wallet or membership mutation.
  Identity registers it separately and requires explicit user consent.
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

## Collaboration invitations

The next complete ordinary-user task is to read an invitation addressed to you,
understand its target, role, validity and site scope, accept that exact invitation,
and inspect the owner's currently linked access-task result. The three commands are
`invitations list`, `invitations show INVITATION_ID` and
`invitations accept INVITATION_ID`. They add no TUI page or invitation database.
`accept` defaults to a read-only preview. Add `--apply` to accept; it first reads
that exact invitation again, then submits its explicit v2 computation permission.
If identity verification is required, use the returned `verification_url`, then
read the same invitation ID. Existing processing may already have accepted it.
The human view includes that link and the contextual readback command.
File viewing, file editing and use of a computing account are shown separately
from administrator roles. When computation is included, the view identifies the
organization as payer and any project-budget constraint, without estimating an amount.

Portal reuses `OrgInvitation`, the canonical recipient and expiry predicates,
`accept_workspace_invitation_by_id`, and the existing task readback service.
The target and current terms belong to the invitation; there is no caller-selected recipient,
site override or invitation secret in command arguments. The pending list is
paged by immutable invitation ID. Detail remains an exact recipient-bound read
after the invitation leaves the pending list. Shared-directory site labels
preserve the original namespace scope rather than implying a single-site grant.

List/show/preview require `sai.collaboration.invitations.read`; `--apply` also requires
`sai.collaboration.invitations.accept`. Both are optional user-consent scopes.
Existing compute, storage, billing and default-account grants stay unchanged.
Normal account eligibility and current inviter authority still apply. A claimed
open invitation can require Identity assurance before acceptance; initial token
claiming stays in its existing browser flow.

The immutable invitation ID is the domain's natural replay identity. A repeat
uses the existing locked acceptance and task generation; it does not issue a
new invitation or restore a subsequently revoked relationship. No automatic
write retry is added. `accepted` is the invitation state. Per-site deliveries
come from the owner's currently linked tasks, and `workspace_available` is a
separate current access check. An administrator can update an accepted directory
invitation's role, validity and linked task; `accepted_at` is historical and does
not prove acceptance of those later terms. A completed task alone never grants
current access.

When organization membership becomes active, Portal preserves an existing valid
default computing account and selects the new organization only when no valid
default exists. Joining another site does not replace a valid global choice.
Acceptance does not authorize an arbitrary preference change. Use the separately
authorized `account defaults` read for the saved choice and site application state.

Contracts: [page](../contracts/collaboration-invitations/v2/README.md) and
[detail/accept](../contracts/collaboration-invitation/v2/README.md).
The previous invitation workflow and optional Identity scopes were deployed.
The v2 capability contract and preview/apply command are deployed with the
paired Portal/CLI components. An old response fails before writing; an old empty
acceptance body is rejected by the paired server. Actual additional consent,
recipient acceptance and applied site access remain separate acceptance work.
Inviter-side member/role management and broader budgets/storage/compute remain
separate gaps; this recipient workflow does not complete those domains.

## Delivery gates

Verify the ordinary user identity, read-only token rejection, revoked membership,
cross-user isolation, concurrent edits, exact replay and stale site receipt.
Exercise actual HTTP through the installed CLI, then the existing transaction
path on MariaDB. Release the paired Portal/client contract and optional Identity
scope before requesting fresh human consent. Use a standard user for production
acceptance; source tests are not proof of a real site applying the preference.

## Discover before invoking

After signing in on a user device, use `sai sites` to obtain published site
names and IDs without having to configure a site first. Pass a returned ID to
the next site-specific command. Directory presence is not permission to use a
site, and the CLI does not select or save one automatically.

`sai describe` returns a compact operation catalogue. Use
`sai describe account set-default` for exact parameter flags/requiredness,
`business_write`, the separate write scope and `account defaults` readback.
This works offline in a base installation. It reveals no profile values and
makes no authorization claim. Session operations and local file downloads have
their own effects; a catalogue entry is never permission to execute it.

The description is generated from the existing parser rather than maintained as
a parallel command list. Added code is limited to syntax serialization and the
source/effect/prerequisite declarations beside command registration; no new
provider or runtime dependency is introduced. The full local suite passed 1112
tests, including discovery-driven native reads and a fake-HTTP preference
write/readback. An installed wheel describes itself with only the standard
library and with config, network and subprocess execution unavailable. Independent review corrected optional-site descriptions and the distinction
between local logout cleanup and acknowledged server revocation. These
are client proofs, not a newly authorized real user-device/VM management change.

The shared CLI was updated once from `d7b0a62e97fa` on 2026-10-10. The 946-file
runtime passed checksum/public-permission readback. A standard user read the
31-operation catalogue with no native PATH and an invalid connection override;
the normal selected entry returned the same catalogue as the inactive canary.
The native GPU TUI still entered/exited a real terminal and restored its settings.
Connection/profile bytes stayed unchanged; no permission, saved preference,
backend service or per-node installation changed. Previous runtime and controlled
rollback archives remain; task staging/helper and operator sessions were cleaned.


## Session boundary for portable acceptance

The previous same-value acceptance used separate local credential files but
shared the provider's native SSO session with the daily read profile. Deleting
those temporary files preserved the daily session; server-side revocation of an
independent management session was not proven. A profile/cache directory is not
a separate Identity session. Before testing targeted logout or revocation,
verify the provider-owned session boundary; never revoke the daily session as
cleanup for an isolated-profile test. No client-side session registry or
administrative substitute for the user's consent is introduced.

The 2026-10-11 acceptance used a clean unprivileged Ubuntu container and the
base wheel, without Slurm, Lustre, shared installations or a Pilot runtime.
The normal device grant's issuer/subject matched the ordinary user's daily
session, while the native session identifiers differed. Minimal OpenID scopes
need not return a username; optional display claims are not identity keys.
The user approved a real temporary account change. Both the change and restoration
produced newer applied site receipts and matching native Slurm observations.
Replaying either intent preserved its original acceptance and did not reapply it;
a stale expectation was rejected. The temporary grant's latest refresh was
rejected after logout. The daily session then refreshed successfully and still
could not write. No computation was submitted. Private receipts retain exact
objects and timestamps; this does not claim coverage of every user device or VM.

For a different-default acceptance, first identify the actual user device/VM and
an explicitly approved target/window. Read the current authorized choices,
save the original value, and use expected-value/idempotency guards for both
change and restoration. Verify each new site receipt and native default; do not
replace a concurrent user choice or count another no-op as site execution proof.
An acceptance may name an older in-flight projection: require a current applied
receipt newer than the pre-change baseline, not equality with an obsolete
acceptance generation. If site application fails, attempt the approved guarded
restoration while the saved value still equals the test target. A failed or
uncertain restoration must remain explicit.

## Use from a user device or isolated user VM

Treat this environment as an ordinary client. An unprivileged container and
resource limits do not establish network isolation. Use an approved client
network with rules enforced outside the guest, keep administration and control
networks inaccessible, and allow only the required service origins and name
resolution. Native commands and internal site credentials are not prerequisites
for these Portal operations.

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
