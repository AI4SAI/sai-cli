# Security Policy

## Reporting

Report suspected vulnerabilities privately to the repository maintainers. Do
not open a public issue containing credentials, tokens, private deployment
details, user data, or an exploit against an active SAI environment.

## Client security boundary

`sai-cli` is an API client, not an authorization boundary. The SAI control
plane and future site-local gateway must independently validate every actor,
scope, site, account selector, and narrowing filter.

The client is expected to:

- keep token caches private and atomic;
- reject insecure remote HTTP by default;
- avoid command-line secret arguments;
- bound response sizes and timeouts;
- redact server error bodies;
- allowlist response fields;
- fail closed rather than query a broader native source.

Never include real secrets, internal addresses, node lists, raw scheduler logs,
or private operational evidence in bug reports or test fixtures.

