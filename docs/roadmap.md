# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

## Site Artifact: controller submission policy

- [x] Minimal `job_submit.lua` submission and modification policy
- [x] Strict versioned GPU policy renderer; account selection uses native facts
- [x] Actual-Lua behavior tests without a Python policy reimplementation
- [x] Snapshot, hot-reload, rollback, failure and performance contracts
- [x] Portal authoritative projection producer
- [x] Matching-version disposable-controller compatibility test
- [x] Live controller canary, measured-peak load gate and duplicate TaskProlog checks retired

Acceptance boundary: one site on the matched Slurm version, with native client
and representative GPU allocation canaries. This does not claim every site,
topology, MPI mapping or scientific application has been revalidated. Detailed
operations evidence is kept outside this repository.

## Site artifact: software module access

- [x] One Tcl load checker over the process's native GIDs, with no remote request
- [x] Versioned inert software/GID data contract and third-software behavior tests
- [x] Matching Portal/site binding release and protected shared publication
- [x] VASP/Gaussian bounded site grant/revoke and module/file-access acceptance

See [software module access](software-access.md). Local Tcl behavior does not
prove a site deployment or refresh the groups of existing sessions.

## Login summary

The [login summary design](login-summary-design.md) defines a compact view of
the applied default identity, authorized funds, unread messages and actionable
access issues. It adds to the existing login help, rules, quota/resource status
and notes, and reuses the workbench's facts and permissions.

- [x] Coordinated Portal/CLI overview contract and local role/scope validation
- [x] `sai status` JSON/plain/Rich panel and Textual Overview, with one shared login fragment
- [ ] Live login latency, privacy, cleanup and user-comprehension validation

Implementation and target deployment coverage are tracked separately; live
acceptance and remaining consumers are recorded in the operations plan.
The existing `auth status` recovery route does not
expose funds or messages; the overview uses the normal CLI read authority.

## Milestone 0.1: read-only jobs CLI

- [x] Installable Python package and `sai` console entry point
- [x] Profile, environment, and command-line configuration precedence
- [x] Protected short-lived token cache
- [x] Existing Bearer token and unmanaged compatibility HMAC bootstrap
- [x] `sai jobs list` and `sai jobs show`
- [x] `sai jobs allocation JOB_ID` against the explicit site gateway snapshot
  (local/fake HTTP; physical assets, utilization and attempt identity remain separate)
- [x] `sai jobs cost` against the independent Portal running-estimate DTO
- [x] `sai resources catalog` against the shared published site catalog DTO
- [x] `sai storage quota-summary` and independent TUI Storage view over Portal
  observations; new storage scope registration is a separate deployment gate
- [x] Explicit `storage native-quota` and TUI source selection over authorized
  on-demand Lustre project quota subjects; native service-UID acceptance pending
- [x] Stable JSON and deterministic table rendering
- [x] Scope/filter validation and no normal-user all scope
- [x] Bounded error mapping and response redaction
- [x] Unit, CLI contract, fake HTTP integration, package, and disclosure tests

Acceptance boundary: local tests and fake HTTP only. This milestone does not
prove a development stack, live scheduler, remote site, package deployment, or
production wrapper.

## Milestone 0.2: control-plane compatibility

- [x] Server-bound `/v1/slurm/cli/*` and `/v1/billing/cli/*` routes with an
  exact `sai-authz` capability and `entrypoint=cli` shell-access check
- [ ] Shared cross-repository request/response fixture (the two repositories'
  focused vectors are aligned, but no single shared artifact is published yet)
- [x] Versioned published site catalog schema and sample shared with Portal
  WebUI and Pilot; job and running-estimate shared artifacts remain separate work
- [ ] Production issuer key/epoch deployment and authenticated devstack smoke
- [ ] SAI Identity OIDC provider/device grant, registered `sai-cli` client, and
  Portal resource-token verifier (owned by the Identity/Portal repositories;
  the current repositories are still pre-migration)
- [ ] Development-stack read-only smoke for self and one account scope
- [ ] Independent Portal settled-billing read contract (`billing.settled.read`)
  and a separately reviewed CLI command
- [ ] Browser/device login via the SAI Identity OIDC Device Authorization Grant
  (the client-side protocol candidate is local; Identity provider/client
  registration, Portal resource-token consumption, and live authentication
  remain gates)
- [ ] Shell completion and package metadata

Acceptance boundary: development control plane. It does not prove live site
facts or production deployment.

## Milestone 0.3: optional TUI

The [unified workbench design](unified-workbench.md) defines shared TUI, WebUI,
and Agent semantics beyond a job list: resource selection, task diagnosis,
results, usage, and Pilot context. Establish those contracts and task flows
first. The [digital-twin design](digital-twin-design.md) keeps hardware 3D work
behind validation of asset, allocation, and telemetry facts. Both documents
are candidate designs, not completed implementation milestones.

- [x] Optional TUI dependency group and interactive `sai tui` entry
- [ ] Jobs, resources, partitions, QOS, and usage navigation model
- [x] TUI running-usage estimate view; the batch `jobs cost` view already
  exposes `final=false`, `as_of`, freshness, price revision, and uncertainty
- [x] Separate TUI allocation inspection over one site snapshot, including exact
  array-task identity, paused refresh and complete F5 replacement (local HTTP only)
- [x] Open in Web for an inspected job using Portal-owned workspace mapping,
  observation comparison and a visible same-origin link (local HTTP/Textual only)
- [x] Explicit project-scoped Tasks with owner-only managed-run history, detail,
  bounded stdout/stderr and output-file pages (local validation; no runtime start)
- [ ] Estimate-to-final replacement without duplicate display or aggregation
- [x] Local-state keyboard interactions and serialized asynchronous refresh
- [ ] Stale-while-revalidate, cancellation, pagination, and bounded empty/error
  states
- [x] Headless resource/job/estimate interactions, HTTP and delayed-response isolation tests

The first [terminal workbench](terminal-workbench.md) supports two-partition
comparison, filtered job list/detail, allocation inspection, and independent
non-final estimates. Allocation shows the response's nodes, CPU/memory, freshness
and restart count with explicit allocated/not-allocated/unavailable states.
It does not provide measured utilization, GPU placement or physical location.
Web navigation rechecks the exact job and workspace and carries the prior
observation as comparison evidence; it does not launch or renew a Pilot task.
Scope changes discard stale requests; network cancellation remains bounded by
the HTTP timeout. Only estimates have local snapshot pages, not job-history
pagination. Native output preview/deep links, settled billing and live
resource views remain unfinished. Native storage shows authorized quota subjects,
not an organization pool aggregate; this is not the full workbench.

Acceptance boundary: TUI contract against fake or development endpoints. It
does not prove real placement, topology, rate data, or production latency.

## Milestone 0.4: site-local capability transport

- [ ] Versioned capability/query/response schemas
- [ ] Control-plane issuer compatibility vectors
- [ ] Site-local billing-visibility capability; the Portal running-estimate
  HTTP contract is implemented, but job visibility alone must not grant it
- [ ] Shared scheduler collector snapshot for jobs and usage estimates, with
  2-15 second TTL, request coalescing, ETag, and freshness
- [ ] Cross-repository site-runtime gateway fixture for verifier, filter
  narrowing, cache isolation, and audit reference; the gateway server is not a
  CLI-wheel module
- [ ] Client capability cache and renewal single-flight
- [x] Explicit direct gateway transport for `jobs list/show`, capability-only
  credentials and versioned `jobs/v1`; cost/catalog/auth remain central
- [x] Independent typed storage grant and `storage.native-quota/v1`; strict
  filesystem/subject binding and no fallback to stored observations
- [ ] Development-stack protocol smoke
- [ ] Contract fixture usable by CLI/TUI, Portal relay, and a separately owned
  site-local read-only Web client
- [ ] Separate site-telemetry batch fixture proving interactive reads cause no
  exposure writes and persistence does not follow the 2-15 second UI cadence

Acceptance boundary: protocol implementation. It does not prove a live remote
site or production package.

The direct-job slice uses on-demand filtered native reads, not the existing
billing collector's cluster-wide/terminal-state cache. Local HTTP and fixture
subprocess tests are distinct from live Slurm, deployed gateway and fleet gates.

## Milestone 0.5: packaging and canary

- [x] Shared client package and optional TUI extra
- [ ] Package-managed legacy wrapper templates
- [ ] Install manifest, forbidden-content guard, and rollback artifact
- [ ] Read-only live scheduler comparison with an authorized sample scope
- [ ] Canary latency, freshness, audit-backlog, and rollback evidence

Production rollout and fleet-wide replacement require a separate operations
plan and approval.

The shared archive, optional TUI dependency bundle, small login integration
Debian package, full-SHA manifest and canary run card are implemented.
Target install/readback, latency and rollback evidence remain separate
operational acceptance gates; package builds do not prove fleet completion.
