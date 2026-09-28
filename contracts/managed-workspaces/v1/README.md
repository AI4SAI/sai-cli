# Managed computation workspace discovery

`compute.workspaces/v1` describes one page of currently readable project choices
for managed computations at an explicit site. The producer is the Identity-only
`GET /v1/compute/cli/workspaces`, requiring `sai.compute.read` and CLI admission.
`limit` is 1–100 (default 50); `cursor` is the last returned workspace key.

The existing project read guard owns active membership and organization-manager
eligibility. Current account, assurance, personal site and project site checks
still apply. Public project visibility does not grant membership. Historical
scheduler accounts, wallets, writable file roots or a running Pilot Session
are not prerequisites for discovering a readable project.

The server orders by immutable project ID ascending, reads only a bounded page,
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
