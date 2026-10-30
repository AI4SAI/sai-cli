# project.member/v1

See the [paired project compute management contract](../../project-compute-enable/v1/README.md) for authority, pagination,
replay and accepted versus applied behavior.

The optional `compute_access_reason` explains an unavailable site's current
observation, using the same project-member reader as the console. It distinguishes
unconfirmed scheduler access, pending/failed/drifting limit synchronization, a
zero submission limit, and the existing identity restriction states. It is null
when access is available or the original observation cannot explain it. These
are current read facts, not new permissions or reasons to repeat enablement.
