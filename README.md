# sai-cli

`sai-cli` is the command-line client for SAI compute services. It provides a
stable, machine-readable interface to Portal-authorized, site-scoped compute
data while keeping authorization decisions out of login-node shell wrappers.

The first implementation milestone is intentionally read-only:

- `sai jobs list` lists jobs in an authorized personal, organization, or
  project scope.
- `sai jobs show` returns one authorized job.
- JSON is the default output. A compact table is available for interactive use.
- The client never sends raw Slurm user filters and does not expose an all-user
  scope.

Job submission, cancellation, resource mutation, TUI views, and the
site-local capability gateway remain roadmap items. See
[docs/roadmap.md](docs/roadmap.md) for the exact boundary.

## Architecture

- [Architecture](docs/architecture.md)
- [Runtime design](docs/runtime-design.md)
- [Portal API contract](docs/portal-api-contract.md)
- [Site-local read plane](docs/site-local-read-plane.md)
- [Roadmap](docs/roadmap.md)

## Development status

This repository was initialized from design work previously maintained in the
SAI Portal repository. The material has been generalized for this standalone
client: deployment-specific hostnames, addresses, paths, and operational
evidence are intentionally not part of this repository.

The repository is currently private and does not yet carry an open-source
license. Do not publish a package or make the repository public until a license
and release policy have been approved.

