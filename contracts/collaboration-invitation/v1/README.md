# Recipient collaboration invitations v1

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
revocation. The client never automatically retries a write. No request body
fields, site override, recipient selector or invitation secret are accepted.

`accepted_at` records historical acceptance. An accepted directory invitation
can later acquire updated roles/validity and a replacement linked task through
its original administrator workflow. Returned terms describe the current row,
not an immutable copy of what was originally accepted. Replaying acceptance
does not newly consent to those later changes. `deliveries` describes the
owner's currently linked access-task group through its authorized presenter; it includes exact task ID,
generation and site. A completed task is historical execution evidence.
`workspace_available` is the original presenter's separate current access result,
not a permission inferred from invitation acceptance. Unknown times remain null.
When an organization membership becomes active, the existing business rule
selects that organization as the default computing account and queues site
synchronization. Acceptance permission includes this bounded domain effect;
it is not permission to choose an arbitrary default account. Inspect the
independently authorized account-default read to observe it. No client computes
grants or queries Slurm/filesystems for this workflow.

The optional scopes, API and client must be released together. Source/schema
validation is not proof of live consent, actual site application or every client
platform. Existing browser invitation routes keep their current consumers.
