# Project invitations from a user client

An authorized project manager invites an existing SAI account by its exact
username. Portal resolves that account, previews the requested terms and creates
the invitation through the original collaboration service. The recipient uses
the existing invitation list, preview and acceptance commands.

This contract covers computing projects and an existing account. It uses a
project member relationship across all of the project's associated sites.
The selected site supplies the entry context. Shared-folder invitations, open
registration and membership changes retain their existing owners.

## Routes and authorization

| Method and path | Scope | Response |
| --- | --- | --- |
| `POST /v1/account/cli/projects/{project_id}/invitations/preview` | `sai.collaboration.members.read` | `project.invitation-preview/v1` |
| `POST /v1/account/cli/projects/{project_id}/invitations` | `sai.collaboration.invitations.write` | `project.invitation-create/v1` |
| `GET /v1/account/cli/project-invitations/{invitation_id}` | `sai.collaboration.members.read` | `project.invitation/v1` |
| `GET /v1/account/cli/project-invitation-requests/{request_id}` | `sai.collaboration.members.read` | `project.invitation-create/v1` |

Every route checks the caller's current project management authority. The
preview resolves one exact username under that authority. It returns no contact
directory, credential, invitation token or private path.

The preview request contains `schema_version: "project.invitation-preview/v1"`,
`site_id`, `invitee_username` and the five term fields: `role`, `compute_enabled`,
`membership_valid_from`, `membership_expires_at` and `ttl_hours`. Creation uses
`schema_version: "project.invitation-create/v1"`, the same fields and the
preview's `invitee_user_id`, with an `Idempotency-Key` header. UTC timestamps
end in `Z`. The member expiry is required, the start may be null, and invitation
validity is 1–720 hours with a default of 72.

## Preview and confirmation

The project object reuses `ProjectComputeRef`. The invitee object contains only
`user_id` and `username`. `allowed_roles` lists the server-approved role choices.
`terms` echoes the normalized request. The client binds project, site, username
and all five terms before showing a confirmation command. It does not derive
management authority from roles, project names or local Unix permissions.

File access, project administration and use of the project computing account
remain separate terms. When computation is included, the parent organization
pays and `uses_project_budget` describes an additional project budget limit.
`relationship_scope` is `global`. Directory site labels describe the existing
project sites, while `site_id` identifies the selected context.

`membership_valid_from` and `membership_expires_at` describe the member's access
window in UTC whole seconds, matching the original membership writer.
`acceptance_expires_at` estimates the effective deadline if sent at preview
time, bounded by both invitation lifetime and member expiry. Human preview
labels that estimate; the created invitation's effective deadline comes from
the original invitation reader. Preview creates no invitation. Human output
generates one complete confirmation command containing the resolved invitee ID
and one request key.

## Creation, replay and readback

Creation returns the original accepted request, project ID, invitation ID,
invitee and `delivery: "message_center"`. The delivery field names the existing
notification channel. It is not a receipt that the recipient read or accepted
the invitation. The client binds the returned request key, project and invitee
to its intent. It does not retry a write automatically.

Request lookup returns the original creation receipt for the same actor and
request key. Replaying the same key and body preserves that receipt. A reused
key with different terms conflicts. The invitation ID leads to the current
manager-authorized detail, including later acceptance, expiry or revocation.
An existing pending invitation returns `409/workspace_invitation_already_pending`
with its `invitation_id`. The client validates this reference and supplies the
existing `projects invitation` recovery command. It never cancels or replaces
the pending invitation.

Detail reuses the original recipient v2 invitation item and linked task
deliveries. It adds the project and invitee references, with no recipient
`next_action`. The client binds the invitation ID and any supplied project,
site or invitee selectors. Delivery status and `workspace_available` retain
their separate original meanings. Acceptance and a completed task do not
replace the current access result.

Unknown response fields are ignored at every modeled level. Unsupported schemas,
malformed fields and mismatched identities or preview terms fail closed.
The examples are synthetic protocol fixtures. Paired source validation is
separate from deployment, real user consent and site application.
