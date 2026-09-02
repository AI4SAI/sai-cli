# sai-cli

`sai-cli` is the command-line client for SAI compute services. It provides a
stable, machine-readable interface to Portal-authorized, site-scoped compute
data while keeping authorization decisions out of login-node shell wrappers.

The first implementation milestone is intentionally read-only:

- `sai jobs list` lists jobs in an authorized personal, organization, or
  project scope.
- `sai jobs show` returns one authorized job.
- `sai jobs cost` shows Portal-authorized, non-final running cost estimates.
- JSON is the default output. A compact table is available for interactive use.
- The client never sends raw Slurm user filters and does not expose an all-user
  scope.

Job submission, cancellation, resource mutation, TUI views, and the site-local
capability gateway remain roadmap items. Running estimates are read from the
independent Portal billing DTO; the CLI has no pricing engine or Slurm reader.
See
[docs/roadmap.md](docs/roadmap.md) for the exact boundary.

The repository also carries a controller-side Slurm policy artifact under
`site/slurm/`. It validates submissions made through any Slurm client; it does
not add a `sai` submission command or grant job mutation rights. See
[docs/job-submit-policy.md](docs/job-submit-policy.md).

Production login-node mode requires the capability-bound Portal issuer and
independent site-read gateway. The issuer resolves `entrypoint=cli` and
requires shell access `enabled`; the gateway verifies the grant and reads only
the authorized native snapshot. The legacy Portal `portal_read` endpoints are
not a production fallback. Code availability does not imply that the issuer,
gateway, keys, or login-node package have been deployed.

## Architecture

- [Architecture](docs/architecture.md)
- [Runtime design](docs/runtime-design.md)
- [Portal API contract](docs/portal-api-contract.md)
- [Site-local read plane](docs/site-local-read-plane.md)
- [Billing / interactive read-plane freeze](docs/billing-read-plane.md)
- [Login-node deployment run card](docs/login-node-deployment.md)
- [Slurm job submit policy](docs/job-submit-policy.md)
- [Roadmap](docs/roadmap.md)
- [Repository guidelines](AGENTS.md)

## Development status

This repository was initialized from design work previously maintained in the
SAI Portal repository. The material has been generalized for this standalone
client: deployment-specific hostnames, addresses, paths, and operational
evidence are intentionally not part of this repository.

The repository is currently private and does not yet carry an open-source
license. Do not publish a package or make the repository public until a license
and release policy have been approved.

## Install for development

Python 3.11 or newer is required. The batch CLI has no third-party runtime
dependency.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/sai --version
```

## Configure

Use a short-lived Bearer token when one is already available:

```bash
export SAI_API_BASE_URL=https://portal.example.org
export SAI_SITE_READ_BASE_URL=https://site-read.example.org
export SAI_SITE_ID=site-a
export SAI_CLUSTER_ID=cluster-a
export SAI_TOKEN='<short-lived-token>'
```

Unmanaged compatibility clients can provide `SAI_API_USERNAME`,
`SAI_API_KEY_ID`, and `SAI_API_SHARED_SECRET` through a protected runtime
environment for the existing HMAC bootstrap. Managed login nodes use only an
injected short-lived `SAI_TOKEN`; no shared secret is installed on a
multi-user node. Neither form belongs in a shell profile or TOML file.

In capability mode the CLI first exchanges the user Bearer for an opaque,
operation-bound site-read capability, then calls the independent site-read
gateway. The capability is never decoded by the CLI and is never accepted from
an environment override or command line.

Non-secret defaults can be stored in `~/.config/sai/config.toml`:

```toml
[profiles.default]
portal_base_url = "https://portal.example.org"
site_read_base_url = "https://site-read.example.org"
site_id = "site-a"
cluster_id = "cluster-a"
```

## Use

```bash
sai jobs list
sai jobs list --scope project-account --account project-example
sai jobs list --states R,PD --partition gpu-standard --format table
sai jobs show 12345
sai jobs cost --states R,PD --format table
```

Connection options are accepted before or after the leaf command, so both
`sai --site site-a jobs list` and `sai jobs list --site site-a` work.

## Verify

```bash
.venv/bin/python -m pytest
.venv/bin/python -m build
python3 scripts/check_public_surface.py
```
