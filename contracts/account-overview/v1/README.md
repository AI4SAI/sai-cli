# Account overview v1

Portal owns this schema and the synthetic sample. The CLI copies these compatibility
artifacts and uses a standard-library allowlist; it imports no Portal runtime.

`GET /v1/account/cli/overview` accepts one `site_id` and optional
`slurm_account_name` (a current authorized runtime or canonical account name).
Without an account selector, Portal uses its existing site-scoped default resolver.
The optional selector lets a login report its applied native account instead of
silently combining a newly selected Portal preference with older site state.

Identity resource authentication, `sai.compute.read` and enabled shell access are
required. Financial fields additionally require `sai.billing.read`; lacking that
scope yields `funds.state=not_authorized` and null amounts. This is a central
read, never a site-read capability or an identity-recovery endpoint.

Cash/credit/project visibility follows the existing workspace and billing owners.
`net_balance` is the signed settlement balance used by the console cash presenter;
`available_credit` is current scope/site Credit after reservations, in SAI Credit
units. It is neither a cash balance nor a guarantee a proposed job can run.
Unused postpaid credit and running cash exposure remain separate. Project budget
visibility cannot disclose its parent organization's cash to a project member.

Inbox items are at most two unread titles from the current user's authorized
identity/site inbox, with exact unread count from the existing message query.
No raw payload, attachments, wallet IDs, ledger or provider data are returned.
Reading does not mark messages read, create funding facts, collect native state,
or trigger a notification. URLs are constructed by the client from its trusted
Portal origin and validated workspace/site, not accepted from message payloads.

Unknown fields are ignored after recursive client allowlisting. Invalid data and
controls fail with a bounded diagnostic. Null is not zero; unavailable identity
returns no funds or inbox. All times are UTC ISO8601 ending in Z. Reads are private,
no-store. The observed_at is the central read time, not a native job/storage sample.
