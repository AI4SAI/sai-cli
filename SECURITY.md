# Security policy

Report a vulnerability through [GitHub private vulnerability reporting](https://github.com/AI4SAI/sai-cli/security/advisories/new).
Do not include credentials, private deployment information or an exploit against
an active system in a public issue. Include the client version, affected command,
expected behavior and a minimal synthetic reproduction when possible.

## Supported versions

During alpha, fixes target the latest published alpha. Keep the previous reviewed
wheel for rollback. A client update does not grant new permission or alter a
server's authorization policy.

## Authority

Local Slurm/Linux/Lustre reads run under the caller's Unix authority. Remote
operations use normal Identity authorization and the owning service's policies.
Native visibility never grants Portal business, billing or write permission.

Credentials are private user-owned files, never command arguments or TOML data.
The client verifies TLS, bounds responses, rejects cross-origin redirects and
filters output. Configuration requires an explicitly trusted service URL;
credentials are not sent during connection discovery.

Management uses each domain's existing scope, concurrency/replay and receipt
contract. An accepted request is not proof that site execution has completed.
