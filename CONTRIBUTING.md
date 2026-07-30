# Contributing

Use focused Conventional Commits such as `docs:`, `feat:`, `fix:`, and
`test:`. Keep documentation, client behavior, and Portal API contract changes
reviewable as separate slices when practical.

Before submitting a change:

1. Run the complete local test suite.
2. Build the source and wheel artifacts.
3. Run the disclosure scan documented by the release workflow.
4. State the exact validation boundary. Local fake HTTP tests do not establish
   development-stack, live scheduler, remote-site, or production behavior.

Public-facing files must use portable examples. Do not commit private
hostnames, addresses, node/rack labels, absolute user paths, credentials, raw
logs, job IDs from active systems, or internal operational worklists.

