# Job Web context

Schema and sample are copied byte-for-byte from Portal's
`contracts/job-web-context/v1`. Portal alone resolves native-account ownership
and current workspace read permission. This client allowlists the returned
fields, binds them to the exact request and constructs a fixed same-origin
console path; it accepts no server-supplied URL.

The request may identify the native READ account by a canonical `workspace_key`
instead of account ID/name. The response schema stays unchanged. This client
binds an explicit workspace selector to the returned workspace exactly, without
treating its business owner ID as the native account ID.

Paired Portal source: `85cb4ba3e`; read-only site selection: `e4df419c9`.
Schema SHA-256: `fd10a07766b272e06ccf24adf3ffa0dc639211de39dcc32628d783061d39f9b7`.
Sample SHA-256: `1511c740e5c116f7af362d4199d66d8164d26161e2724f50d7d630082419353e`.
These source checks do not establish deployment or real-site acceptance.

The earlier observation travels as user context, not authority or a permanent
execution ID. Known submission/restart changes prevent automatic navigation;
the browser independently authenticates and reads the current allocation.
See [the API contract](../../../docs/portal-api-contract.md#job-workspace-navigation).
