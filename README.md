# sai-cli

`sai-cli` is the command-line client for SAI compute services. It provides a
stable, machine-readable interface to Portal-authorized, site-scoped compute
data while keeping authorization decisions out of login-node shell wrappers.

The first implementation milestone is intentionally read-only:

- `sai jobs list` lists jobs in an authorized personal, organization, or
  project scope.
- `sai jobs show` returns one authorized job.
- `sai jobs allocation JOB_ID` reads a job's current allocation snapshot from
  an explicitly configured capability-bound site gateway.
- `sai jobs cost` shows Portal-authorized, non-final running cost estimates.
- `sai resources catalog` reads the same published compute and storage catalog
  used by WebUI and the SAI Pilot resource tool.
- `sai storage quota-summary --workspace-key org:example` reads authorized
  effective/target quotas and timestamped stored usage, without filesystem access.
- JSON is the default output. A compact table is available for interactive use.
- The client never sends raw Slurm user filters and does not expose an all-user
  scope.
- `sai auth login` uses a browser-approved device flow once; later commands
  renew a short-lived access token from a revocable local device session, so a
  user does not log in again for every SSH connection.

The optional `sai tui` workbench compares published resources, narrows job
queries, inspects job details and reads non-final running estimates through
the same clients. Install with `pip install '.[tui]'` and run `sai tui` from
an interactive terminal. See [the terminal workbench](docs/terminal-workbench.md).

Job submission, cancellation and resource mutation remain roadmap items.
Jobs can optionally read directly from the site-local capability gateway
through a protected `site_read_base_url` profile setting; deployment is separate.
Running estimates are read from the
independent Portal billing DTO; the CLI has no pricing engine or Slurm reader.
See
[docs/roadmap.md](docs/roadmap.md) for the exact boundary.

The repository also carries a controller-side Slurm policy artifact under
`site/slurm/`. It validates submissions made through any Slurm client; it does
not add a `sai` submission command or grant job mutation rights. See
[docs/job-submit-policy.md](docs/job-submit-policy.md).

The separate site login fragment selects the working directory for the user's
existing default Slurm identity. It belongs to the shared site shell environment,
not to the CLI command or wheel. See [docs/login-workdir.md](docs/login-workdir.md).

Production login-node mode requires the capability-bound Portal CLI surface.
The legacy shared Portal endpoint uses `portal_read` policy and may accept
`agent_only`; managed wrappers therefore set `SAI_REQUIRE_SITE_CAPABILITY=1`
and use only the server-bound `/cli/` routes, which enforce shell access
`enabled`. Code availability does not imply that Portal keys/routes or a
login-node package have been deployed.

## Architecture

- [Architecture](docs/architecture.md)
- [Runtime design](docs/runtime-design.md)
- [Portal API contract](docs/portal-api-contract.md)
- [Site-local read plane](docs/site-local-read-plane.md)
- [Billing / interactive read-plane freeze](docs/billing-read-plane.md)
- [Login-node deployment run card](docs/login-node-deployment.md)
- [Shared platform runtime layout](docs/platform-runtime-layout.md)
- [CLI login and long-lived device sessions](docs/cli-auth.md)
- [Login summary product design](docs/login-summary-design.md) (proposed)
- [Slurm job submit policy](docs/job-submit-policy.md)
- [Roadmap](docs/roadmap.md)
- [Terminal workbench](docs/terminal-workbench.md)
- [Product principles](PRODUCT.md)
- [Unified TUI, WebUI, and Agent workbench (candidate design)](docs/unified-workbench.md)
- [Hardware digital twin and 3D view (candidate design)](docs/digital-twin-design.md)
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

Managed nodes use the shared client under `/opt/sai/cli`,
with a small Debian integration package owning `/usr/bin/sai`. Installation,
configuration, canary, and rollback are documented in the
[deployment run card](docs/login-node-deployment.md).

## Configure

Use a short-lived Bearer token when one is already available:

```bash
export SAI_API_BASE_URL=https://portal.example.org
export SAI_SITE_ID=site-a
export SAI_TOKEN='<short-lived-token>'
export SAI_REQUIRE_SITE_CAPABILITY=1
```

Unmanaged compatibility clients may provide `SAI_API_USERNAME`,
`SAI_API_KEY_ID`, and `SAI_API_SHARED_SECRET` through a protected runtime
environment. Managed login nodes use the SAI Identity OIDC device flow and do
not carry an HMAC secret. Capability-bound CLI routes reject Portal-issued
legacy credentials. An already-issued short-lived Identity `SAI_TOKEN` remains a
process-local emergency/compatibility input; neither form belongs in a shell
profile or TOML file.

For a user-managed or login-node installation, configure the non-secret Portal
origin/site once and run `sai auth login`. It prints a one-time browser URL and
device code, then stores only a protected rotating refresh credential. See
[docs/cli-auth.md](docs/cli-auth.md).

In capability mode the CLI first exchanges the user Bearer for an opaque,
operation-bound site-read capability, then calls the matching server-bound CLI
route. The capability is never decoded by the CLI. It is obtained only from
the Portal issuer; it is never accepted from a profile, wrapper, shell
startup file, argv, or log.

Non-secret defaults can be stored in `~/.config/sai/config.toml`:

```toml
[profiles.default]
base_url = "https://portal.example.org"
identity_issuer = "https://id.example.org/realms/sai"
oidc_client_id = "sai-cli"
oidc_scope = "openid offline_access sai.compute.read sai.billing.read sai.storage.read"
oidc_resource = "sai-portal"
site_id = "site-a"
```

## Use

```bash
sai jobs list
sai jobs list --scope project-account --account project-example
sai jobs list --states R,PD --partition gpu-standard --format table
sai jobs show 12345
sai jobs cost --states R,PD --format table
sai resources catalog --site site-a --format table
```

Connection options are accepted before or after the leaf command, so both
`sai --site site-a jobs list` and `sai jobs list --site site-a` work.

The default jobs transport retains the Portal response contract. Opting into
the direct gateway selects the versioned `jobs/v1` response with an exact
subject, native observation time and truncation flag; it does not invent a
Portal membership role. See the [transport contract](docs/portal-api-contract.md#direct-site-job-reads).

## Verify

```bash
.venv/bin/python -m pytest
.venv/bin/python -m build
python3 scripts/check_public_surface.py
```
