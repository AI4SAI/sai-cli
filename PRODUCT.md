# Product

## Register

product

## Purpose

`sai-cli` is the shared SAI interface for people, scripts and user-controlled
agents. It connects two everyday needs: fast cluster queries integrated with
SSH habits, and authorized queries and management of the SAI control plane.
It runs on SAI login/compute nodes, a user's own device, or a dedicated isolated
SAI VM. Pilot is one consumer, not a requirement for another agent to use SAI.

The 2026-10-09 user clarification supersedes the earlier summary-and-cost-only
interpretation. Retiring an overloaded full-screen workbench does not remove
local query integration or Agent management from the product. The existing
summary and cost commands remain useful delivered parts, not the entire scope.

## People and agents

| Consumer | Primary use | Interaction |
| --- | --- | --- |
| Person on a login/compute node | Queries like `sqm`, `sqa`, `gpu`, `cpu` and `quota`, plus account, budget and cost information | Familiar aliases and short commands, useful defaults, compact tables and optional focused interaction |
| Agent or script on any supported host | Query SAI and manage the user's authorized Portal resources | Stable structured results, discoverable operations, bounded errors and verifiable mutation outcomes |

These are presentation choices over common operations. An agent may expose a
broader command surface, but gains no authority beyond its user and the user's
explicit delegation. A person can use the same management commands. The CLI
contains no model loop, chat store or separate Agent runtime.

## Execution and authority

Local Slurm/Linux/Lustre observations should execute under the current Unix
identity, on the selected local site, without a Portal login or gateway round
trip. Integrate the existing shared helpers and aliases; reuse or migrate their
implementation once instead of maintaining competing native readers. Local
means a local client of the site's native systems, not a full cluster scan or
remote SSH to every compute node.

Membership, account ownership, budgets, commercial prices, approvals and final
charges belong to Portal. Query and management commands call the corresponding
business APIs. Remote native reads use the selected site's authorized gateway.
Both local and remote observations identify their source and scope; native
visibility is not proof of Portal membership, billing permission or asset truth.
A failed remote read must not silently retry with different local authority.

Portal management reuses its existing domain services, role checks, operation
records and task-first site effects. The CLI requests an action and reports its
actual outcome; it never writes business databases, uses a site-admin secret,
or treats an accepted asynchronous task as complete. Existing approval rules
apply to their operations, without a second generic approval system in the CLI.

## Deployment

- Login/compute nodes consume one shared `/opt/sai` publication and the existing
  shell integration. Native queries stay local and do not require per-node
  services or per-command mounts.
- A user's device installs the client independently and obtains that user's
  Identity authorization for Portal and remote reads. It needs neither a
  shared NFS mount nor an active Pilot session.
- A dedicated user VM uses the same client and per-user credentials. Network
  proximity or VM isolation grants no extra scope. Local adapters are available
  only where the native environment and user identity are actually provided.

## Experience and acceptance

Preserve the shell, familiar aliases, scriptability and fast repeated queries.
Use authorized names and existing login context to avoid repeated technical-ID
entry. Querying another account does not change the submission account, working
directory or payer; management changes are explicit separate operations.

Verify native query counts and latency on login and compute nodes, including
operation without Portal connectivity or OAuth credentials. Verify that human
and JSON output describe the same observation. GPU allocation and scheduler
capacity must remain distinct from measured utilization.

Verify Agent queries and one complete management action on both a user device
and a dedicated VM through normal user authority: accepted intent, execution,
receipt, errors and readback. A request must not become a repeated mutation on
retry. CLI/API checks do not establish human usability or complete deployment.

## Current delivery

The client implements central business summaries and costs, authorized remote
reads, and explicit local job/resource queries. The shared package contains thin
`stat_job`/`stat_job_all` entries for the latter. Shared publication and account
alias migration passed ordinary-user checks on a login and a compute node;
see the [delivery record](docs/terminal-scope.md#local-job-delivery).
GPU/CPU resource helpers also use the shared CLI and have passed ordinary-user
login/compute checks. Native quota is implemented with shared-helper activation
and live acceptance tracked separately. General Portal management and full
portable Agent management acceptance remain
unfinished. See [the runtime plan](docs/runtime-design.md)
and [roadmap](docs/roadmap.md). Current read-only scope is an implementation
milestone, not a permanent product restriction.

WebUI/Pilot product modules and the role-based hardware digital twin remain
with their existing owners. [Hardware design](docs/digital-twin-design.md) records
asset-based parametric 3D and Agent-readable facts; 3D is not a prerequisite for
local queries or user-authorized Portal management.
