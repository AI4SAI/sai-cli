# Managed computation workspace discovery

`compute.workspaces/v1` describes one page of currently readable personal, organization and project account choices
for managed computations at an explicit site. The producer is the Identity-only
`GET /v1/compute/cli/workspaces`, requiring `sai.compute.read` and CLI admission.
`limit` is 1–100 (default 50); `cursor` is the last returned workspace key.
Optional `workspace_key` narrows discovery to one exact readable account and
is mutually exclusive with `cursor`. Success contains exactly that key as the
sole item, with `has_more=false` and `next_cursor=null`; consumers reject a
different key or an empty resolution. An inaccessible key is denied without
revealing its name. This resolves an explicit terminal preselection without
walking all pages or inventing a catalog entry.

The existing read guards enforce personal ownership, current organization membership
and project membership or organization-manager eligibility. Current account,
assurance and both personal/account site checks still apply. Public project visibility does not grant membership. Historical
scheduler accounts, wallets, writable file roots or a running Pilot Session
are not prerequisites for discovering a readable account.

The server orders by the complete immutable workspace key ascending, reads only a bounded page,
and rechecks the cursor against the current actor/site readable set. A revoked
cursor is an invalid continuation; return to the first page explicitly. Choices
are observations, not grants. Every subsequent Run/file read authorizes again.

Labels are display text, never selectors. `organization_label` is present and
nullable. The server applies existing profile redaction and visible control
escapes, then bounds each label to 256 Unicode code points. The response contains
no filesystem paths, wallet facts, account credentials, user filters or runtime
identities. Duplicate labels do not imply the same workspace.

Consumers allowlist nested fields, bind site/schema, validate timestamps and
page size, reject duplicate workspace keys and a repeated requested cursor,
and require `next_cursor` to equal the last item exactly when `has_more=true`.
The full list is not implied by one page. No automatic page drain or persisted
context is required. This shared schema and sample are byte-identical in Portal
and CLI; local validation does not establish deployment or live-site acceptance.
