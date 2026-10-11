# Security Policy

## Reporting

Report suspected vulnerabilities privately to the repository maintainers. Do
not open a public issue containing credentials, tokens, private deployment
details, user data, or an exploit against an active SAI environment.

## Client security boundary

Remote `sai-cli` operations are API clients, not authorization boundaries. The
SAI control plane and deployed site-local read gateway independently validate
their actors, scopes, sites, account selectors and narrowing filters. Explicit
local Slurm/Linux/Lustre queries run under the caller's actual Unix authority;
that visibility grants no Portal business permission.

The client is expected to:

- keep token caches private and atomic;
- reject insecure remote HTTP by default;
- avoid command-line secret arguments;
- bound response sizes and timeouts;
- redact server error bodies;
- allowlist response fields;
- fail closed rather than query a broader native source.

Business writes use the existing domain service, separate user scope and its
concurrency, replay, audit and receipt contract. Read permissions do not grant
write authority. A client confirmation or preview does not replace server policy
or turn an accepted asynchronous request into a completed operation.

Never include real secrets, internal addresses, node lists, raw scheduler logs,
or private operational evidence in bug reports or test fixtures.

