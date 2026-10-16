# Recipient collaboration invitations v2

Portal owns invitation identity, recipient binding, expiry, acceptance and access
tasks. This contract exposes only invitations addressed to the current Identity
user, including an open invitation already claimed through the original browser
flow. The CLI never receives or accepts an invitation token. Pending invitation
list pages reuse the original validity predicate, sorted by immutable ID with a
bounded exclusive cursor. Detail remains readable for the same recipient after
acceptance or expiry; it does not enumerate other users or contacts.

List/detail require `sai.collaboration.invitations.read`. Accept requires the
independent `sai.collaboration.invitations.accept` scope and the original domain's
current eligibility checks. The stable invitation ID identifies the acceptance operation. Repeating that ID follows the original locked
acceptance behavior; it does not create another invitation or reset a later
revocation. The client never automatically retries a write. Acceptance requires exactly `schema_version: "collaboration.invitation-accept/v2"`
and the boolean `compute_enabled` read from this invitation. Missing/old bodies
are rejected before the writer runs; a changed compute permission returns
`409/invitation_permissions_changed`. No site override, recipient selector or
invitation secret is accepted.

`compute_enabled` is the explicit computation permission. It is independent of
`has_compute_resources`, which describes the target's resources, and `role`,
which also carries governance. For project invitations, `read` plus false means
view files; `write` plus false means edit files; `write` plus true adds use of the
project's computing account. An `admin` role does not imply computation by itself.
Organization invitations include organization-account computation; directory
invitations do not. The organization pays for computation; `uses_project_budget`
adds the project's budget constraint, not a separate payer. These are
responsibility labels, not a price or an immediate charge.

`invitations accept ID` only previews this detail response and requires read
permission. `--apply` rereads the exact invitation, validates v2, then sends one
POST with its explicit compute permission. The response uses this same detail
schema. Old v1 responses fail with an upgrade diagnostic before any POST; there
is no inferred permission, extra consent record or automatic retry.

`accepted_at` records historical acceptance. An accepted directory invitation
can later acquire updated roles/validity and a replacement linked task through
its original administrator workflow. Returned terms describe the current row,
not an immutable copy of what was originally accepted. Replaying acceptance
does not newly consent to those later changes. `deliveries` describes the
owner's currently linked access-task group through its authorized presenter; it includes exact task ID,
generation and site. A completed task is historical execution evidence.
`workspace_available` is the original presenter's separate current access result,
not a permission inferred from invitation acceptance. Unknown times remain null.
When an organization membership becomes active, Portal preserves an existing
valid default computing account and initializes the new organization as default
only when no valid default exists. A valid global choice remains unchanged when
it is unavailable at the new site; association delivery is separate. Acceptance
does not authorize an arbitrary preference change. Inspect the independently
authorized account-default read for the saved choice and site application state.
No client computes grants or queries Slurm/filesystems for this workflow.

The v2 API and client require a coordinated release; existing optional scopes are unchanged. Source/schema
validation is not proof of live consent, actual site application or every client
platform. Existing browser invitation routes keep their current consumers.
