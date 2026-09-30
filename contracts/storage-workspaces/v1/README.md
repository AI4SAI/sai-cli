# Storage workspace discovery

`storage.workspaces/v1` is a bounded page of readable storage scope names at an
explicit site. The Identity-only producer is
`GET /v1/account/cli/storage/workspaces`, requiring `sai.storage.read` and the
existing enabled-shell CLI admission. It returns only safe names, exact keys,
site and query time, with no quota, path, wallet, scheduler or identity details.

`limit` is 1–100 (default 50). `cursor` is the preceding page's final key.
Optional `workspace_key` narrows the read to one exact choice and is mutually
exclusive with `cursor`; success contains exactly that item and no continuation.
An inaccessible exact key is denied, not replaced with another choice or an
empty successful resolution. A revoked cursor requires an explicit first-page
refresh. Each request rechecks current visibility.

The storage quota reader owns membership rules: the actor's personal scope,
active organizations with current membership, and active projects with current
project membership or organization management authority. The directory lists
only scopes with active access at the requested site. It does not reuse task
read, submit, file-write or billing permission. Existing explicit quota-summary
reads keep their own unavailable-state semantics when site access is absent.

A choice does not grant quota access or promise either source is available.
Stored summaries and native Lustre quota reads authorize independently. Discovery
reads only bounded central metadata; it does not query native storage, issue a
capability, load the full Web topology or obtain a site's administrative secret.

Labels are display text; keys are selectors. Duplicate names remain distinct.
`organization_label` is present and nullable. The server applies the existing
profile redaction and visible control escapes, bounded to 256 Unicode code
points. Clients recursively allowlist fields, validate schema/site/page size
and time, reject duplicate keys and repeated cursors, and require a nonempty
page with its final key as `next_cursor` exactly when `has_more=true`. Exact
reads additionally bind the sole returned key to the request.

CLI JSON, table output and the TUI use this same contract. The schema and sample
are byte-identical in Portal and CLI. Local fixtures establish contract behavior,
not production installation, native quota access or site availability.
