# Product

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

## Product delivery

The user outcome is a complete useful task: install, authorize when needed,
discover the relevant operation, act within the user's rights, and inspect the
result. Local queries stay immediately useful in an existing SSH environment.
Command count, test count and source merges are supporting evidence, not product
acceptance. Track task completion, repeated technical input, recovery effort,
and operating cost.

[The task and delivery map](docs/product-delivery.md) owns the current capability
gaps, next complete journeys and proposed public distribution strategy. It
distinguishes the established human/Agent scope from licensing and publication
decisions that remain unapproved. Historical implementation records do not
automatically select the next feature.

## People and agents

| Consumer | Primary use | Interaction |
| --- | --- | --- |
| Person on a login/compute node | Queries like `sqm`, `sqa`, `gpu`, `cpu` and `quota`, plus account, budget and cost information | Familiar aliases and short commands, useful defaults, compact tables and focused keyboard interaction |
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
login/compute checks. Native quota and the thin `quota` function are also
published and verified against native counters in those two environments.
Default-account management is deployed through the existing Portal writer and
site receipts. Actual change/restoration, new site application, replay and
independent authorization revocation are verified on a clean Linux container;
broader business and device coverage remains open. See
[the management boundary](docs/portal-management.md),
[runtime plan](docs/runtime-design.md) and [roadmap](docs/roadmap.md).

Settled job-charge reads are also deployed with bounded ordinary-user evidence.
Published-site discovery and the bundled Agent skill are deployed with bounded
ordinary-user reads; see the [delivery map](docs/product-delivery.md#shared-first-use-delivery).
Account/member, project/budget, storage and compute
management beyond the default-account action remain product gaps; a working
read command does not establish their management coverage.

Recipient invitation discovery, acceptance and original task readback are the
next paired source candidate, with separate optional scopes. Inviter-side
management remains planned. See the [task map](docs/product-delivery.md).

WebUI/Pilot product modules and the role-based hardware digital twin remain
with their existing owners. [Hardware design](docs/digital-twin-design.md) records
asset-based parametric 3D and Agent-readable facts; 3D is not a prerequisite for
local queries or user-authorized Portal management.
