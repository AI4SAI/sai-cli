# Recipient collaboration invitation page v2

`GET /v1/account/cli/invitations` requires `sai.collaboration.invitations.read`.
It lists currently valid pending invitations addressed to the current Identity
user, including an open invitation already claimed through the original browser
flow. It never enumerates other users, contacts or invitation tokens.

Pages reuse the original validity predicate, sort by immutable invitation ID and
accept a bounded exclusive cursor plus `limit` from 1 to 100. `next_cursor` is the
last returned ID only when `has_more` is true. Each item uses the same explicit
file/compute permissions and payer facts as the
[invitation detail](../../collaboration-invitation/v2/README.md).

The client rejects v1 instead of inferring computation from `role` or
`has_compute_resources`. API and client activation must be coordinated; schema
validation alone is not production or actual recipient acceptance.
