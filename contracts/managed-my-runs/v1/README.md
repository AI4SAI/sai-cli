# My managed Run receipts

`GET /v1/compute/cli/my-runs` (Identity resource compute READ) and
`GET /v1/account/compute/my-runs` (browser READ) return the authenticated caller's
Run receipts across all currently readable workspaces at one explicit `site_id`.
The only other query fields are `limit` (1–100, default 50) and `cursor` (Run
reference). Caller, user, workspace, raw account and cluster selectors are rejected.

`compute.my-runs/v1` has `site_id`, `source=portal_run_receipts`, `queried_at`,
`items`, `next_cursor` and `has_more`. Every item contains the existing managed
Run fields plus `workspace_key`, `workspace_label` and nullable
`organization_label`. Labels use the current authorized directory's redaction.
Detail, file, statistics and cost reads use that Run reference and workspace
through their existing endpoints and repeat their own permissions.

Ordering is `accepted_at DESC, run_ref DESC`. The next cursor is the last item
only when more authorized records exist. A supplied cursor must remain visible
to this caller at this site; revocation or an unrelated cursor is a bounded 400
error requiring a fresh page. This is keyset pagination over current authority,
not a frozen snapshot. Source/query failures are unavailable, never empty success.

This read neither changes compute selection nor requires submission, payment or
file permission. CLI admission still requires enabled shell access; browser
admission retains `agent_only` support. Native queue observations, native-only
history, automatic Job/Run association and final billing are separate contracts.
Existing single-workspace `compute.runs/v1` is unchanged. Consumers ignore future
fields only through an explicit allowlisted model; they must preserve actor/site,
workspace, integer, timestamp and cursor validation.
