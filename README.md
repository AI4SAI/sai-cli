# SAI CLI

Fast cluster queries for people. Structured SAI operations for scripts and Agents.

Use familiar SSH commands on a cluster, or connect your own computer and Agent
through normal SAI authorization. The client contains no model loop and does
not require Pilot.

## On a cluster

```bash
sqm                 # your jobs
sqa                 # the applied computing account and its child projects
gpu                 # GPU allocation and available nodes
cpu                 # CPU and memory allocation
quota               # quota for the current directory
sai tui             # select jobs/nodes with arrows or a click; q exits
```

These queries run locally under your Unix identity. In the TUI, `p` pauses or
resumes updates, Enter inspects a row, and `c` requests that job's running cost
through your authorized SAI account. Allocation is distinct from utilization;
running estimates are distinct from settled charges.

The job selector discovers your native Slurm accounts; quota lets you choose an
actual directory. Job details lead with the allocation and a compact CPU/NUMA
and GPU connection view when a current hardware record is available. `i` expands
hardware details; arrow/page keys scroll, `r` refreshes, and Escape returns to the
selected row. Native account names are also available as
JSON through `sai account local`. These reads do not change your shell or defaults.

Native adapters have been exercised with Slurm 26.05.1 and Lustre 2.17;
other native versions are not yet qualified.

## On your computer

Python 3.11+ is required. This alpha is qualified on Linux; macOS and Windows
are not yet qualified. Download the wheel and SHA-256 checksum from the
[versioned releases](https://github.com/AI4SAI/sai-cli/releases), verify
the checksum, then install in an isolated environment with pipx:

```bash
pipx install ./sai_cli-0.2.0a2-py3-none-any.whl
sai configure https://console.example.org --format table
sai auth login
sai sites --format table
```

Use your service's trusted URL in place of the example. Confirm the login code
in your browser, then choose a returned site explicitly:

```bash
sai resources catalog --site site-a --format table
sai account defaults --site site-a --format table
```

The catalogue contains published specifications and prices. Account defaults
shows your authorized choices; neither command changes an account or grants
site access. Configuration preserves existing profiles and credentials.
See [first use and recovery](docs/getting-started.md) for wheel installation,
additional permissions, multiple services and upgrade/rollback.

The base client has no third-party runtime dependency. For the optional interface, install the downloaded wheel with its UI extra:
`pipx install './sai_cli-0.2.0a2-py3-none-any.whl[tui]'`. It needs an interactive
terminal. Local views require the corresponding Slurm/Lustre tools on that host.
The `0.2.0a2` candidate includes recorded hardware connections, CPU locality and
selected-site connection discovery. Use the wheel filename from the reviewed
release you downloaded; older release assets are retained unchanged.

## With your Agent

```bash
sai describe
sai describe account set-default
sai skill --format markdown
```

`describe` is the installed command authority. `skill` exports matching Agent
instructions for the host you choose; neither requires login or network access.
Commands return JSON by default, with separate structured errors and documented
exit codes. A task can request its missing permissions with
`auth login --for`, followed by the user's browser confirmation.

The client supports native queue/resource/quota reads, account and cost queries,
job allocation and recorded-run outputs, default-account changes and recipient
invitation acceptance. Broader project, storage and compute management is not
implemented. Read permission does not grant write permission. The called service
owns authorization and reports whether a change was accepted or applied.

## Learn more

- [First useful task](docs/getting-started.md)
- [Human and Agent scope](docs/terminal-scope.md)
- [Supported management and receipts](docs/portal-management.md)
- [Architecture and ownership](docs/architecture.md)
- [Versioned API contracts](docs/portal-api-contract.md)
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md)
- [Licensing and third-party notices](THIRD_PARTY.md)

First-party client code, the shared native projection and bundled Agent guidance
are licensed under Apache-2.0. The separate Slurm source patch retains its upstream
GPL terms and is excluded from Python distributions. The repository's site
integration artifacts have their own deployment roles; installing the Python
client never installs or changes a scheduler, login profile or storage service.

The [interconnect contract](contracts/node-interconnect/v1/README.md) joins recorded CPU/NUMA, PCIe, GPU and fabric
relationships to an exact live allocation via `--with-interconnect`. Local reads
stay native; the existing site gateway uses `include_interconnect=true`.
Deployment and its validation boundary are recorded in
[terminal scope](docs/terminal-scope.md#interconnect-correction-2026-10-12).
