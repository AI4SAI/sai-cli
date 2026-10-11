# sai-cli

`sai-cli` is the shared SAI command-line interface for humans, scripts and
user-controlled agents. Its target covers fast cluster-local queries integrated
with existing SSH aliases, and authorized Portal queries and management from
user devices or dedicated isolated SAI user VMs.

Start with [your first useful task](docs/getting-started.md): existing cluster
aliases, or a portable installation with normal sign-in and explicit site choice.
`sai skill --format markdown` supplies the matching Agent guidance offline.

Local query integration reuses the `sqm`, `sqa`, `gpu`, `cpu` and `quota` habits
under the current Unix identity, with no central login or gateway hop.
`sai jobs local` and `sai resources local` implement native job and resource
queries. `sai storage local-quota` reads a local path's Lustre project quota;
Default-account management is deployed. An independent Linux client has passed
an actual account change, new site receipt and native readback, restoration and
isolated-session revocation; see [portable management](docs/portal-management.md).
This validates the first management action, not every business domain or platform.
Business operations retain Portal's authority.
See [the product scope](PRODUCT.md).
The [task and delivery map](docs/product-delivery.md) distinguishes implemented
capabilities, complete user journeys and the proposed public distribution.

The existing account/access information, funds, budget and cost commands remain
available. Start with `sai`
for a brief account summary, then return to work. Redirecting `sai` produces
JSON; explicit commands such as `sai status` keep their JSON default. Use explicit
cost queries; a full terminal workbench is not the product target. See
[terminal scope](docs/terminal-scope.md).

For a local Slurm query, use `sai jobs local --format table`, or
`sai jobs local -A research --format table`. Remote organization job reads include only Portal-authorized child projects,
preserving each project's member visibility. The paired scope contract migration
is documented in [the API contract](docs/portal-api-contract.md#organization-job-scope).

For agents, `sai describe` lists the installed operations without logging in or
loading a profile. `sai describe account set-default` expands one command's
parameters, permissions and receipt/replay rules; `sai describe jobs` narrows
the list. It does not check current authorization. See the
[description contract](contracts/cli-description/v1/README.md).

JSON is the default for agents and
scripts. Shared `stat_job`/`stat_job_all` now use this same implementation;
`sqa`/`ja` select the applied Slurm account and its native child accounts in
new login shells. Use `-A ACCOUNT --with-subaccounts` for the same explicit
subtree query; plain `-A ACCOUNT` stays exact.
See the [native command contract](contracts/native-jobs/v1/README.md) for exact
filter semantics and the [shared rollout](docs/login-node-deployment.md).

For local capacity, `sai resources local --kind gpu --format table` shows a
partition overview. Add a partition name or `--details` for node observations.
The shared package provides `stat_gpu`/`stat_cpu` wrappers for existing aliases.
Those helpers include node details by default. Resource tables use the optional
`sai-cli[tui]` Rich dependency, included in the shared runtime: GPU cells preserve
native Slurm IDX positions; CPU partitions show per-node allocation bars and
load/free-memory reports. JSON needs no UI dependency. Job tables retain the
compact fixed columns; quota retains usage, quota, limit and grace columns.
See [native resources](contracts/native-resources/v1/README.md) for the distinction
between allocations, blocked capacity, node reports and actual utilization.

`sai storage local-quota --format table` reads the current directory's native
Lustre project quota. Supply a path when needed; JSON preserves exact counters
and grace state. This local read does not require a workspace ID or Portal login.
See the [local quota contract](contracts/local-quota/v1/README.md).

The implemented remote API surface includes:

- `sai sites` lists published site IDs and names before you choose a site.
  It needs no configured site. Use a returned ID with `--site` on the next
  command; listing a site does not grant account, compute or file access.
- `sai account defaults` discovers accounts available at the selected site and
  shows the user's global default and site application receipts.
- `sai account set-default ACCOUNT_ID --if-current auto --request-id REQUEST_KEY`
  requests an explicit global default change through Portal. It requires separate
  user consent, the last saved default (`auto` means no explicit choice), and a
  stable request key. Acceptance is separate from site application; see
  [portable management](docs/portal-management.md).
- `sai runs read RUN_REF --artifact-ref ARTIFACT_REF --workspace-key project:example`
  reads one bounded UTF-8 output section. Current file permission is checked
  independently; no Pilot session or model window is needed.
- `sai runs download RUN_REF --artifact-ref ARTIFACT_REF --workspace-key project:example --output result.bin`
  saves the complete authorized file, including binary contents. Existing paths
  are never replaced. A failed or interrupted transfer removes its temporary
  file; retry starts from the beginning. This download contract requires paired
  Center and site deployment.
- `sai runs recent` reads your recorded work across currently readable accounts
  at the selected site, with bounded history pages and authorized names.
- `sai runs workspaces` discovers currently readable personal, organization and
  project task scopes by name.
  `sai storage workspaces` discovers readable storage scopes at the selected site.
  Both accept `--workspace-key` for an exact authorized name lookup.
  These directories remain batch reads, separate from the account summary.
- `sai status --format tui` shows a compact login identity, funds and unread-message
  panel, then returns to the shell. JSON remains the default for scripts.
  Plain `sai` reuses that account read, showing plain text in a terminal and JSON
  in a pipe or file. It requires no optional formatting dependency.
- `sai jobs list` lists jobs in an authorized personal, organization, or
  project scope.
- `sai jobs show` returns one authorized job.
- `sai jobs allocation JOB_ID` reads a job's current allocation snapshot from
  an explicitly configured capability-bound site gateway.
- `sai jobs placement JOB_ID` joins that observation to operator-recorded asset
  locations when the site enables this independent read; it does not prove the
  current physical machine behind a scheduler name.
- `sai jobs cost JOB_ID` reads one current job's non-final cost estimate from the
  same authorized observation. Omit the ID to read the authorized scope.
- `sai jobs charges` lists settled job expenses from Portal. Use `--job-id` to
  find a scheduler ID, then its returned record key for exact final amounts.
- `sai runs list/show/logs/files --workspace-key project:example` reads your
  managed computations, including completed runs, bounded logs and output-file
  metadata. Task records and current file reads remain separate sources.
- `sai runs cost RUN_REF --workspace-key project:example` explicitly reads
  final cost, independently of task metadata. It requires `sai.billing.read`
  and current account access; funding details follow the same financial
  visibility as the console. Missing amounts remain unknown.
- `sai runs stats RUN_REF --workspace-key project:example` reads an explicit
  native step observation: average cumulative CPU seconds and step task RSS.
  It uses compute READ, independently of file and billing access. Unknown
  values remain null; these are not GPU or whole-node utilization metrics.
- `sai runs placement RUN_REF --workspace-key project:example` reads current
  node registrations with the native allocation bound to that exact Run.
  The server derives and verifies execution evidence; a reused job number
  cannot silently redirect the read to a different computation.
- `sai resources catalog` reads the same published compute and storage catalog
  used by WebUI and the SAI Pilot resource tool.
- `sai storage quota-summary --workspace-key org:example` reads authorized
  effective/target quotas and timestamped stored usage, without filesystem access.
- `sai storage native-quota --workspace-key project:example` reads authorized
  Lustre project quota subjects on demand through the configured site gateway.
- Explicit commands default to JSON. A compact table is available for interactive use.
- The client never sends raw Slurm user filters and does not expose an all-user
  scope.
- `sai auth login` uses a browser-approved device flow once; later commands
  renew a short-lived access token from a revocable local device session, so a
  user does not log in again for every SSH connection.

`sai tui` opens focused keyboard queries. On cluster hosts it starts with an
available native query: jobs, GPU, CPU or quota. Use arrows and Enter to select,
`r` to refresh, `c` to read the selected job's non-final cost and `q` to return
to the shell. The scope/partition chooser replaces typed IDs; quota offers the
current directory and Home. Native reads use the same readers and resource
visuals as the aliases, without a Portal login or gateway round trip.

Account information is a separate on-demand view, with an authorized account
chooser. Cost and account reads retain their existing Identity/Portal permissions.
No read changes the shell directory or submission account. `--view` selects an
initial query; `--language zh-CN|en-US` selects interface copy. `--account` selects
the business overview only; local jobs use the applied login account or self.

Install the optional interface with `pip install '.[tui]'` (Textual and Rich).
It requires an interactive terminal. `sai status --format tui` remains the
one-shot Rich summary used at login. Plain `sai`, explicit JSON commands and
aliases retain their behavior. The old Portal/Pilot workbench remains retired.
See [terminal scope](docs/terminal-scope.md) for source and delivery boundaries.

The first Portal management operation shares the existing default-account writer
and site tasks. Broader management remains planned and must retain each domain's
task/approval semantics. It works independently of a Pilot Session or model
runtime. Agent command coverage does not expand the user's permissions.
Job submission, cancellation and resource mutation remain roadmap items.
Jobs can optionally read directly from the site-local capability gateway
through a protected `site_read_base_url` profile setting; deployment is separate.
Running estimates are read from the
independent Portal billing DTO; native observations do not create a local pricing engine.
See
[docs/roadmap.md](docs/roadmap.md) for the exact boundary.

The repository also carries a controller-side Slurm policy artifact under
`site/slurm/`. It validates submissions made through any Slurm client; it does
not add a `sai` submission command or grant job mutation rights. See
[docs/job-submit-policy.md](docs/job-submit-policy.md).

The separate site login fragment selects the working directory for the user's
existing default Slurm identity. It belongs to the shared site shell environment,
not to the CLI command or wheel. See [docs/login-workdir.md](docs/login-workdir.md).

The shared Tcl module preflight checks the current process's numeric groups and
offers a short access hint without a network request. It is a separate site
artifact; see [software module access](docs/software-access.md) for its trusted
binding, publication and validation boundaries.

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
- [Portable Portal management](docs/portal-management.md)
- [Login summary contract and design](docs/login-summary-design.md)
- [Slurm job submit policy](docs/job-submit-policy.md)
- [Roadmap](docs/roadmap.md)
- [Terminal scope and feature disposition](docs/terminal-scope.md)
- [Previous terminal deployment record](docs/terminal-workbench.md)
- [Product principles](PRODUCT.md)
- [Shared WebUI, terminal, and Agent semantics](docs/unified-workbench.md)
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
the root-owned shared settings `/opt/sai/cli/config.toml`, and a small Debian
integration package owning `/usr/bin/sai`. Installation,
configuration, canary, and rollback are documented in the
[deployment run card](docs/login-node-deployment.md).

## Configure

Use an already-issued short-lived Identity access token for a single process:

```bash
export SAI_API_BASE_URL=https://portal.example.org
export SAI_SITE_ID=site-a
export SAI_TOKEN='<short-lived-identity-token>'
export SAI_REQUIRE_SITE_CAPABILITY=1
```

All current HTTP commands use SAI Identity authentication. Implemented native local
queries use the existing Unix/native authority independently. `SAI_TOKEN` is process-local
and is never cached; it does not belong in a shell profile or TOML file.
Legacy HMAC exchange and its bearer cache are retired. `SAI_API_USERNAME`,
`SAI_API_KEY_ID`, `SAI_API_SHARED_SECRET`, and TOML `username`/`key_id` settings
are rejected before any request. The corresponding command-line options have
been removed. Unset the named environment variables and remove the retired
fields from the selected TOML profile before running `sai auth login`.
An empty retired environment variable is still rejected.

This authentication retirement is deployed in the paired Portal/CLI release.
Remaining production acceptance gates are tracked in [the roadmap](docs/roadmap.md).

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

On a user device, `site_id` may be omitted while signing in and discovering
sites. After `sai auth login`, use `sai sites --format table`, then select a
returned ID explicitly, for example `sai account defaults --site site-a`.

## Use

```bash
sai
sai jobs cost --format table
sai jobs cost 12345 --format table
sai jobs charges --job-id 12345
sai jobs charges slurm:site-a:67890 --site site-a --format table
sai status --format json
sai jobs list
sai jobs list --scope project-account --account project-example
sai jobs list --workspace-key project:example
sai jobs list --states R,PD --partition gpu-standard --format table
sai jobs show 12345
sai jobs cost --states R,PD --format table
sai resources catalog --site site-a --format table
sai runs list --workspace-key project:example --site site-a
sai runs logs run-example --workspace-key project:example --stream stderr --format table
```

Connection options are accepted before or after the leaf command, so both
`sai --site site-a jobs list` and `sai jobs list --site site-a` work.

`--workspace-key` selects the business account scope; Portal resolves its native
compute account. It cannot be combined with `--account` or `--account-id`.
An omitted `--scope` follows the workspace kind; an explicit conflicting scope
is rejected. These are job command selectors; the compact summary does not
accept job or storage scope options.

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
