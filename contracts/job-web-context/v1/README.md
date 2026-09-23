# Job Web context

Schema and sample are copied byte-for-byte from Portal's
`contracts/job-web-context/v1`. Portal alone resolves native-account ownership
and current workspace read permission. This client allowlists the returned
fields, binds them to the exact request and constructs a fixed same-origin
console path; it accepts no server-supplied URL.

The earlier observation travels as user context, not authority or a permanent
execution ID. Known submission/restart changes prevent automatic navigation;
the browser independently authenticates and reads the current allocation.
See [the API contract](../../../docs/portal-api-contract.md#job-workspace-navigation).
