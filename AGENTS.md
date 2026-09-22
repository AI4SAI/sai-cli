# Repository Guidelines

## Read First

- Read `README.md`, `docs/architecture.md`, `docs/runtime-design.md`, and
  `docs/roadmap.md` before changing command behavior or ownership boundaries.
- Read `docs/portal-api-contract.md` before changing requests or response
  models. A Portal contract change requires coordinated compatibility work in
  both repositories.
- Read `docs/site-local-read-plane.md` before adding a transport, capability,
  cache, gateway, TUI, resource, storage, or usage feature.
- Read `docs/platform-runtime-layout.md` before changing shared installation
  prefixes or login integration. Platform commands do not belong in the
  development-toolchain tree or receive per-command NFS mounts.
- This repository is currently private and has no approved open-source
  license. Do not publish packages, releases, tags, or make the repository
  public until maintainers approve a license and release policy.

## Long-Running Work And Goals

- Any long-running development, migration, release, or cross-repository task
  must have an explicit persistent goal. Create it at the beginning when none
  exists, keep the execution plan aligned with it, and check it again after
  interruptions or context compaction.
- Keep detailed progress in the active plan. Update the persistent goal to
  `complete` immediately when its objective and required verification are
  finished. Mark it `blocked` only under the goal tool's repeated-blocker
  rules; difficulty, partial progress, or low context are not blockers.
- Do not leave a completed objective with an active goal, and do not mark a
  goal complete while Portal migration, validation, commit, or push work named
  by that goal remains unfinished.

## Ownership Boundaries

- `sai-identity` owns account identity, credentials, MFA, sessions, consent,
  OIDC/OAuth subjects, and shared profile. Portal owns membership, account
  ownership, site access, policy, authorization, and final billing facts.
- A future site-local read gateway may verify a narrow signed capability,
  further restrict filters, read native facts, cache briefly, and buffer audit
  records. It must not become an authorization or write service.
- `sai-cli` parses explicit user intent, obtains short-lived credentials (via
  the SAI Identity OIDC Device Authorization Grant in managed mode), calls an
  authorized endpoint, validates an allowlisted DTO, and renders output.
  It must not query Slurm, storage, identity databases/administrative APIs, or
  broad site-agent endpoints directly; the registered OIDC protocol endpoint is
  the sole identity interaction.
- Read permission never implies submit, cancel, hold, requeue, QOS mutation,
  quota mutation, wallet, or ledger permission.

## Current Implementation Facts

- Python 3.11+ is required.
- The batch CLI has no third-party runtime dependency.
- The implemented surface is `sai jobs list`, `sai jobs show`, and the
  non-final `sai jobs cost` running-estimate view, plus `sai resources catalog`
  for published specifications and prices (not live capacity or eligibility).
- JSON is the default machine interface; table output is an explicit
  presentation mode.
- Development compatibility can call Portal `GET /v1/slurm/jobs`, detail, and
  `GET /v1/billing/running-estimates`. Managed production mode first obtains
  an opaque site-read capability and calls the server-bound
  `/v1/slurm/cli/*` or `/v1/billing/cli/*` routes. A direct site-local gateway
  transport is available for job list/detail when explicitly configured.
  The optional TUI reuses catalog/jobs/estimate clients; live resource capacity,
  task-result/Pilot handoff, placement and storage usage remain roadmap items.
  Running estimates come only from the server DTO; the CLI does not price jobs.
- `site/slurm/job_submit.lua` is a controller deployment artifact, not a CLI
  command or wheel module. It consumes only a validated controller-local
  snapshot and performs no per-submission file, network, database, subprocess,
  authn-relay, or site-read-gateway call.
- `site/shell/default_workdir.bash` is a shared site login artifact, not a CLI
  command or wheel module. It reads only the current user's native default
  association and lineage for the configured Slurm cluster, without a new
  authorization service, cache, identity preference, or privileged helper.
- Portal owns the authoritative account/project/policy projection. This
  repository owns the strict projection-to-Lua renderer and submit-time
  evaluator; native Slurm associations remain the final account authorization
  boundary.
- The legacy Portal endpoints use `portal_read` policy, which permits
  `agent_only`. Production wrappers must force the server-bound capability/CLI
  routes; Portal re-resolves `entrypoint=cli` and enforces shell access
  `enabled`. Code support alone does not prove the Identity provider, Portal
  resource-token verifier, keys/routes, or login-node package have been
  deployed.
- Supported user scopes are `self`, `personal-account`, `org-account`, and
  `project-account`. There is no normal-user all scope or raw user filter.
- Resource catalogs are site-scoped published data. Managed reads use the
  Identity-only `/v1/account/cli/sites/{site_id}/resource-catalog` route without
  a site-read capability. Catalog visibility does not grant site/job/file access.
- Direct job reads use TOML-only `site_read_base_url`, require capability mode,
  and send only `X-SAI-Capability` to that origin. The versioned gateway jobs/v1
  DTO differs from the default Portal JSON; no transport failure may trigger a
  fallback. Cost, catalog and authentication remain on their central routes.

## Inherited Portal Engineering Lessons

The standalone repository inherits the applicable system lessons from the SAI
Portal codebase. When a task changes both repositories, read the current Portal
repository guidelines and the newest relevant contract/task record before
editing either side. Do not copy private collaboration logs into this repo.

### Control Plane And Site Plane

- The central transactional database is the business source of truth. Local
  SQLite files, CLI caches, site caches, scheduler state, and test fixtures are
  not interchangeable with that source of truth.
- Center and site execution are separate planes. Center services express
  authorized intent through durable records and bounded APIs. Site components
  execute or observe native state. SSH is an operator/deployment channel, never
  an application runtime adapter.
- A center web request must not acquire a broad site-agent secret and directly
  probe a remote site as the steady-state interactive path. Use a controlled
  relay, asynchronous worker, signed snapshot, or the narrow site-local read
  capability architecture.
- Site packages must not import center ORM, migration, Django, WebUI, wallet,
  or ledger code. Read-only site packages must also exclude provisioning,
  scheduler mutation, quota mutation, and identity-admin authority.

### Durable Mutation Semantics

- The current CLI is read-only. Any future write command requires a separate
  architecture review; adding an HTTP verb to the client is not sufficient.
- Site-affecting mutations are task-first. The center records an idempotent
  intent, the site executes it, and center final facts advance only from the
  receipt for the exact object incarnation. A stale receipt must not mutate a
  replacement object.
- Future write commands need explicit idempotency keys, accepted/executed/
  failed states, retry semantics, audit records, and readback. Never present a
  queued or uncertain operation as successful.
- Do not add synchronous SSH fallbacks, direct native command fallbacks, broad
  exception fallbacks, or client-side fake success when a durable path fails.

### Identity, Workspace, Site, And Billing Dimensions

- Personal account, organization account, independent project, site, default
  billing account, shell access, job visibility, and billing visibility are
  distinct dimensions. Do not collapse them into a single mode or infer one
  from another.
- Account ownership comes from explicit control-plane objects. Do not infer it
  from scheduler account prefixes, Unix groups, a default site, or a public
  project flag.
- Missing or non-active site access fails closed. A configured default site is
  not evidence that a workspace has active access.
- Membership validity includes effective and expiry windows. Scheduled,
  expired, removed, or replaced memberships do not inherit current visibility.
- Scheduler billing resources can support limits and estimates, but the
  control-plane ledger remains the final monetary source of truth. Never label
  a running estimate as a charge, balance, or settled cost.

### API And Failure Semantics

- Keep stable JSON field names unless a coordinated, intentional contract
  migration says otherwise. Route handlers stay thin; policy belongs in a
  service layer and DTO normalization belongs at a named boundary.
- Fail closed with a bounded operator/user diagnostic. Do not use guessed
  defaults, silent `except` fallbacks, empty-list fake success, or compatibility
  catch-alls that hide a missing provider, source, or permission.
- A native source returning data outside the authorized filter is not harmless.
  Server-side secondary filtering and client allowlisting are both required.
- Preserve the distinction among live queue state, synchronized history,
  resource metadata, cached observability, running estimates, and settled
  billing facts. A convenient data source is not automatically valid for a
  different semantic purpose.

### Packaging And Production Operations

- Shared platform scripts and the CLI are published once on NFS. Compute nodes
  consume the same files; do not create per-node runtime copies, CLI packages,
  release state or script distribution as the normal update mechanism.
- Reuse the established shared profile and PATH. A new function does not justify
  a new top-level mount, bootstrap, service or configuration hierarchy.
- Separate a one-time mount/entrypoint migration from routine software releases.
  A shared program update must not require client fstab edits or fleet package
  upgrades. Node-local OS components and private credentials keep their own roles.
- Runtime roles receive the smallest dependency and credential set needed for
  their job. Optional CLI/TUI dependencies must not leak into center API,
  management UI, or site service packages.
- Login-node wrappers are package-managed compatibility shims. Inventory and
  checksum existing files, stage a versioned artifact, canary through an
  explicit path, switch atomically, and retain package-level rollback. Never
  hand-edit a production command directory as the rollout mechanism.
- Treat production, production-like, and hardware-test nodes as
  operator-owned. Collect read-only preflight evidence before mutation, keep
  the change bounded and reversible, and separate canary proof from fleet
  completion.
- Do not place secrets, real deployment configuration, private keys, or raw
  production evidence in source, docs, command examples, package artifacts, or
  shell history.

### Collaboration And Repository Hygiene

- Preserve user changes in dirty worktrees. For cross-repository landing, use
  an isolated branch/worktree, integrate one finished slice at a time, verify
  the remote branch after push, and avoid mixing unrelated work.
- After interruption or context compaction, resume from the newest explicit
  continuation point. Historical taskboards and old chat are evidence, not an
  automatic backlog.
- Keep implementation records short and concrete: environment, command,
  sample/fake object, cleanup, result, and what was not verified. Portal-owned
  collaboration records retain their repository timestamp convention.
- Delete obsolete compatibility paths once the current product direction no
  longer needs them. A compatibility bridge must have a named current consumer,
  migration boundary, and removal condition.

## Security Rules

- Never accept Bearer tokens, HMAC secrets, passwords, or other credentials as
  command-line arguments. They leak through process listings and shell history.
- Never store tokens or secrets in TOML profiles. `SAI_TOKEN` is process-local;
  unmanaged compatibility HMAC bootstrap reads its secret from the protected
  runtime environment and caches only the returned short-lived token. Managed
  login nodes use the SAI Identity device flow and a protected rotating
  refresh credential; the wrapper rejects HMAC inputs.
- Token cache directories are user-owned `0700`; cache files are regular,
  user-owned `0600` files written by atomic replacement. Reject symbolic links,
  unsafe permissions, oversized payloads, and read races.
- Config files influence the credential destination. Reject symbolic links,
  unsafe ownership, and group/world-writable config files even though config
  files contain no secrets.
- Reject non-loopback plain HTTP unless the user makes the explicit
  development-only override. Do not weaken TLS verification.
- Bound HTTP timeouts and response sizes. Do not add automatic broad retries or
  redirects to another trust origin.
- Reduce HTTP errors to a short code/message/request ID. Never echo arbitrary
  nested error bodies, HTML, native stderr, raw provider payloads, private
  paths, credentials, or addresses.
- Response models are allowlists. Unknown fields, scripts, environment, paths,
  raw scheduler data, wallet, and ledger fields never pass through to output.
- Reject control characters and invalid types before rendering. Table output
  must not permit terminal escape injection.
- All authorization and filter validation is repeated server-side. Client
  validation improves ergonomics and reduces accidental calls; it is not a
  security boundary.

## CLI And Contract Discipline

- Keep connection options valid both before the command and after the leaf
  command. Both `sai --site site-a jobs list` and
  `sai jobs list --site site-a` are supported contracts.
- Keep user-facing scope values hyphenated and map them explicitly to Portal's
  underscore values.
- `self` rejects account selectors. Personal, organization, and project account
  scopes require exactly one authorized account name or ID selector.
- State, partition, account, site, cluster, job ID, and limit options may only
  narrow a request. Do not expose undocumented query parameters.
- Keep `source_preference=live` fixed until a separately designed historical
  contract exists. A source failure must not trigger broad accounting reads.
- Additive server fields are ignored until explicitly modeled. Removing or
  changing a modeled field requires a coordinated versioned migration.
- Stdout contains successful data only. Diagnostics go to stderr. Preserve the
  documented exit codes and structured JSON error shape.

## Coding Style

### Engineering Taste

- Start with the user-visible invariant and one authoritative owner.
- Keep scripts to a few clear operations using existing tools. Do not hide
  complexity in long lines, nested helpers or custom deployment frameworks.
- Every check needs a real business or protocol reason; preserve valid native
  input. Identifier rules do not constrain arbitrary filenames.
- Prefer removing a mistaken rule over adding a guard, fallback, cache or service.
- Judge the whole operating model: one shared publication, few moving parts,
  simple updates and rollback. Passing tests cannot justify an unmaintainable design.
- Keep compute nodes clean. Node-local infrastructure changes need explicit scope;
  ordinary platform scripts and CLI code are consumed from NFS.
- Finish confirmed fixes, verify real user behavior, and remove task-created
  residue. Preserve existing configuration, workloads and user data.

- Use the existing `src/` package layout, type hints, frozen dataclasses for
  value objects, and small modules with explicit ownership.
- Prefer Python standard-library structured APIs over ad hoc string parsing.
- Keep command handlers thin. Put configuration, authentication, transport,
  contract, and rendering behavior in their corresponding modules.
- Avoid broad exception fallbacks inside domain code. The CLI boundary may
  convert unexpected exceptions to a generic, non-sensitive internal error.
- Add comments only where a security or protocol choice is not evident from
  the code.

## Tests And Validation

Run before every code commit:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m build
python3 scripts/check_public_surface.py
git diff --check
```

- Add negative tests for scope expansion, invalid filters, weak permissions,
  symlinks, expired credentials, malformed DTOs, response-size limits, HTTP
  failures, and sensitive-field redaction when modifying adjacent behavior.
- Use a local fake HTTP server for request mapping and installed-wheel smoke;
  do not use a mock-only test as the sole proof of transport behavior.
- Inspect sdist and wheel contents. Documentation and security guidance belong
  in the sdist; the wheel should contain only runtime code and package metadata.
- Pin third-party CI actions to reviewed commit SHAs and keep workflow
  permissions minimal.
- Local unit and fake HTTP results do not prove Portal devstack compatibility,
  live Slurm data, a site-local gateway, login-node packaging, or production.
  State those boundaries exactly.

## Public-Surface Discipline

- Public-facing examples use generic product-family wording and placeholder
  sites, accounts, partitions, and nodes.
- Do not commit private hostnames, domains, addresses, node/rack lists, absolute
  user paths, credentials, raw logs, live job IDs, serials, hardware maps,
  internal worklists, or production evidence.
- Run `scripts/check_public_surface.py` and a task-specific denylist scan before
  every push. A test vector may use an otherwise blocked generic pattern only
  with the narrow `public-scan: allow-test-vector` marker in `tests/`.
- Keep live benchmarks and operations evidence outside this repository. Publish
  only sanitized summaries with an explicit environment and validation scope.

## Documentation And Release

- Keep `README.md`, architecture, runtime, API contract, site-local design, and
  roadmap consistent with implemented behavior.
- Do not present roadmap endpoints, capability verification, TUI behavior, or
  package rollout as implemented.
- Use focused Conventional Commits. Keep design migration, implementation,
  Portal ownership cleanup, and release changes independently reviewable.
- Do not create a tag or GitHub release merely because local tests and package
  builds pass. Licensing, public metadata, cross-repository compatibility, and
  release approval are separate gates.

## Lessons Learned

- A parser can pass tests while contradicting documented argument order. Test
  commands exactly as users will type them, including options after leaf
  subcommands.
- A configuration file contains no credential but can redirect credentials to
  another origin. Its ownership and write permissions are security-relevant.
- Atomic cache replacement alone is insufficient. Reads must reject symlinks,
  weak permissions, oversized files, and replacement races.
- Dropping unknown top-level fields is not enough. Every nested job field must
  be typed, bounded, allowlisted, and safe for terminal rendering.
- A center-authorized API and a future site-local capability gateway are
  different validation levels. Sharing DTOs must not collapse that distinction.
- An empty repository with successful builds is not automatically ready for
  public release. License selection and release policy require explicit owner
  approval.
- Disk headroom is part of reliable development in constrained environments.
  Prefer reproducible caches and build artifacts for cleanup, recheck free
  space after long tool sessions, and never delete uncommitted project data.
