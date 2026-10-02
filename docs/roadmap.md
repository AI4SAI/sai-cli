# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

Checkmarks cover the implementation or evidence stated on that line. They do
not imply production activation or completion of a paired rollout.

## Next release gate: basic job reads

The next formal release covers `jobs.list`, `jobs.detail` and `jobs.allocation`.
The source, role packages and a bounded native candidate probe are available;
the [candidate record](site-local-read-plane.md#isolated-native-http-acceptance)
uses temporary signing inputs and is separate from this release gate.

- [x] Publish the versioned read-gateway runtime with its required dependencies,
  managed environment, verifier keys, policy epoch and revocation inputs; bind
  the existing HTTPS read origin and verify the intended service UID
  (2026-10-01 basic deployment and bounded real-user list acceptance)
- [x] Exercise the actual Identity client and Portal resource-token verifier
  with an ordinary authorized user, then obtain capabilities from the actual
  Portal issuer under current CLI/shell and workspace policy
- [x] Verify real-user self and authorized account lists through the shared CLI
  and native gateway; empty results matched independent native reads, and an
  unauthorized account was denied
- [ ] Verify positive detail/allocation on naturally available authorized jobs
  and the remaining Portal consuming paths; the accepted list scopes were empty
- [x] Correlate actual Center issuance with production journal start/finish pairs
  by capability ID digest, subject, operation and limit
- [ ] Verify audit collection beyond the local journal and production failure handling
- [x] Hold one real capability until expiry: the direct read was rejected,
  then normal issuance restored the read without changing server policy
- [x] Retain gateway package/runtime and configuration rollback materials;
  exercise HTTPS routing and shared-CLI rollback/restoration without static changes
- [x] Revoke one normally issued test capability by JTI and reload the existing
  gateway: old lease rejected before expiry, normal acquisition/read succeeds;
  original inputs restored only after expiry. This is not membership revocation
- [ ] Exercise full gateway package/runtime recovery and repeat authorized reads

Use the existing [shared release model](login-node-deployment.md) and the
separately owned gateway role. Asset publication, registered placement, native
storage, Run statistics, GPU telemetry and 3D are independent slices, not
prerequisites for basic job reads. The unified observation implementation keeps
pricing at Center and requires no site price bundle.

- [x] Pair and publish the [unified job-observation implementation](billing-read-plane.md):
  same-observation optional Portal estimates and complete billing/v1 gateway reads;
  later TUI selected-job Cost integration was paired into production on 2026-10-02,
  with positive current-job cost acceptance still separate.

The [multi-site topology decision](site-local-read-plane.md#explicit-site-selection-and-ingress-topology)
preserves explicit user site choice and permits independent or shared ingress.
Record it now; implement and validate additional site routing after this gate,
without treating the first center ingress as a mandatory global transit point.

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
  (paired contract/local HTTP checks and a separate bounded native candidate
  probe; physical assets, utilization and attempt identity remain separate)
- [x] `sai jobs cost` against the independent Portal running-estimate DTO
- [x] Independent `jobs placement` and TUI registration view, sharing the
  operator-recorded `jobs.placement/v1` projection with WebUI and Pilot;
  site opt-in, asset review/publication and live acceptance remain separate
- [x] `sai resources catalog` against the shared published site catalog DTO
- [x] `sai storage quota-summary` and independent TUI Storage view over Portal
  observations; new storage scope registration is a separate deployment gate
- [x] Explicit `storage native-quota` and TUI source selection over authorized
  on-demand Lustre project quota subjects; native service-UID acceptance pending
- [x] Stable JSON and deterministic table rendering
- [x] Scope/filter validation and no normal-user all scope
- [x] Bounded error mapping and response redaction
- [x] Unit, CLI contract, fake HTTP integration, package, and disclosure tests

Acceptance boundary: local contract/HTTP checks, plus the separately recorded
native candidate check for list/allocation. That temporary worker does not
prove the formal service, real issuer/user chain or production wrapper.

## Milestone 0.2: control-plane compatibility

- [x] Server-bound `/v1/slurm/cli/*` and `/v1/billing/cli/*` routes with an
  exact `sai-authz` capability and `entrypoint=cli` shell-access check
- [x] Paired schemas and samples in `contracts/` for allocation, registration,
  managed Runs/cost/statistics, workspace discovery, quota and published catalog;
  each contract records its source and validation boundary
- [x] Portal issuer/verifier and CLI consumer compatibility vectors for exact
  job and independent running-estimate grants
- [x] Browser/device login, rotating protected refresh credentials and bounded
  refresh/revocation in the CLI, with local protocol/HTTP tests
- [x] Deployed Identity device-client registration, Portal resource-token
  verification and production capability key/epoch acceptance for the CLI user
- [ ] Development-stack read-only smoke for self and one account scope
- [ ] General settled-billing read command beyond the implemented per-Run
  final-cost contract; read authority remains independent of job visibility
- [x] Python package metadata and installation entrypoint
- [ ] Shell completion

Acceptance boundary: source compatibility, local integration and the bounded
production user-list/lease checks above. Shared files alone do not establish
production registration, deployed keys or a successful real-user read.

## Milestone 0.3: optional TUI

The [unified workbench design](unified-workbench.md) defines shared TUI, WebUI,
and Agent semantics beyond a job list: resource selection, task diagnosis,
results, usage, and Pilot context. Establish those contracts and task flows
first. The [digital-twin design](digital-twin-design.md) keeps hardware 3D work
behind validation of asset, allocation, and telemetry facts. Both documents
are candidate designs, not completed implementation milestones.

- [x] Optional TUI dependency group and interactive `sai tui` entry
- [x] Five-view navigation and published partition/QOS metadata; resource
  eligibility and admission remain separate from catalog presentation
- [x] Explicit resource candidate, independent two-item comparison and shared
  console-to-Pilot preparation intent without requiring an existing job;
  current eligibility and concrete proposal validation stay server-owned
- [x] TUI selected-job Cost mode over one central native observation and price,
  with independent billing scope; duplicate estimate list removed and paired
  installation completed. Batch `jobs cost` keeps the complete-scope contract
- [x] Separate TUI allocation inspection over one site snapshot, including exact
  array-task identity, paused refresh and complete F5 replacement (local HTTP only)
- [x] Open in Web for an inspected job using Portal-owned workspace mapping,
  observation comparison and a visible same-origin link (local HTTP/Textual only)
- [x] Explicit project-scoped Tasks with owner-only managed-run history, detail,
  bounded stdout/stderr and output-file pages (local validation; no runtime start)
- [x] Exact managed-run Web navigation to the independently authorized console
  task page, without requiring an active scheduler account or starting Pilot
- [x] Bounded discovery of readable task projects with safe display names,
  explicit selection and the same current project/site read authority
- [x] Independent storage-name discovery and exact authorized name resolution
  for explicit task/storage selections, without raw-key editing or native probes
- [x] Bilingual task workflow, contextual actions and narrow-screen evidence
  layout, checked with local HTTP and rendered views
- [x] Shared browse/inspection/summary layout across the five views, current-view
  Back and polling-aware actions; local rendered and HTTP checks
- [ ] SSH terminal diversity and long-session experience acceptance
- [x] Bounded real SSH/PTY task evidence checks: 14-minute Chinese run, English
  monochrome, three sizes, delayed-read resize, revocation recovery and cleanup
- [ ] Estimate-to-final replacement without duplicate display or aggregation
- [x] Explicit per-Run final cost with shared Portal graph validation, independent
  billing permission, role-filtered funding components and console continuation
- [x] Bounded production-user historical Run detail, stdout, output and final-cost
  reads, plus headless TUI same-output Web reference and narrow selection retention;
  these reads do not establish a complete new computation
- [x] Paired console/Pilot reference handoff deployed; user confirmed the original
  conversation and file reference are visible
- [x] Paired bounded text-content source and Web/TUI/JSON readers; production deployment remains separate
- [ ] Result workflow: deploy direct inspection, obtain required outputs, then
  optionally bring an explicit question to Pilot; visibility alone is insufficient
- [x] Explicit native Run step statistics shared with WebUI and Pilot; bounded
  owner-UID Slurm reads, execution/step coverage checks and unknown sample time
- [x] Paired site statistics role installation and ordinary-user CLI/API/native
  no-sample response, with existing file and independent gateway reads preserved
- [ ] Positive running-step CPU/RSS and full Web/Pilot native statistics acceptance
- [x] Current Run-bound allocation and node registration across TUI/Web/Pilot,
  reusing the existing signed gateway and registration/scene components
- [ ] Paired Run-placement gateway deployment and real-asset acceptance
- [x] Local-state keyboard interactions and serialized asynchronous refresh
- [x] Bounded empty/error states, paged managed tasks and scope directories
- [x] Headless resource/job/estimate interactions, HTTP and delayed-response isolation tests

The first [terminal workbench](terminal-workbench.md) supports two-partition
comparison, filtered job list/detail, allocation inspection, and independently
authorized non-final costs within the selected job. Allocation shows the response's nodes, CPU/memory, freshness
and restart count with explicit allocated/not-allocated/unavailable states.
It does not provide measured utilization or physical GPU placement. The separate
registration action joins operator-recorded rack/U locations to the same
response's allocation; a scheduler name does not prove current physical identity.
Web navigation rechecks the exact job and workspace and carries the prior
observation as comparison evidence; it does not launch or renew a Pilot task.
Scope changes discard stale requests; network cancellation remains bounded by
the HTTP timeout. Cost inspection has one job observation, not a second paged
list. Managed Tasks have server keyset pages and an exact Web detail link.
Selected output continuation through the console to the original Pilot Session
is deployed; user confirmation covers conversation and file-reference visibility.
Preview/input actions have separate local evidence. Direct result inspection and
retrieval, useful follow-up analysis and the complete computation remain open;
the handoff is an auxiliary action, not the result page's primary outcome.
Explicit final-cost association and the
[`compute.run-stats/v1` endpoints/helper](../contracts/managed-run-stats/v1/README.md)
are implemented in paired source. The statistics path uses bounded owner-UID
native reads; it does not provide GPU or whole-node utilization. Its site role is now installed and a real ordinary-user no-sample
application chain passed. Positive running statistics and complete Web/Pilot
acceptance remain open.
Estimate-to-final replacement and full resource eligibility views remain
unfinished. Native storage shows authorized quota subjects, not an organization
pool aggregate. The TUI discards late results and bounds HTTP calls; this is not
a claim of interruptible network requests or stale-while-revalidate behavior.

Acceptance boundary: local HTTP/rendered checks and the separately recorded
[bounded SSH/PTY runs](ssh-terminal-acceptance.md) with synthetic facts. These
do not prove production authentication, physical placement, telemetry, terminal
font diversity or unbounded long-session stability.

## Milestone 0.4: site-local capability transport

- [x] Versioned capability/query/response contracts and strict validators for
  exact job operations, allocation and independent billing/storage reads
- [x] Control-plane issuer compatibility vectors and capability/filter negative
  checks against the separately packaged site gateway
- [x] Independent `billing.running-estimate` grant; job visibility grants no
  billing permission, and Center-owned missing prices remain unavailable/null
- [x] Native on-demand job reads, request-bound filtering, ETag and freshness;
  no dependency on the billing collector's cluster-wide snapshot
- [x] Shared allocation schema/sample and real local HTTP/native-substitute
  gateway fixtures; the gateway server is not a CLI-wheel module
- [x] Protected client capability cache and bounded renewal retry
- [x] Explicit direct gateway transport for `jobs list/show`, capability-only
  credentials and versioned `jobs/v1`; cost/catalog/auth remain central
- [x] Independent typed storage grant and `storage.native-quota/v1`; strict
  filesystem/subject binding and no fallback to stored observations
- [ ] Development-stack protocol smoke
- [x] CLI/TUI and Portal/Web allocation consumers reuse the shared contract and
  existing gateway, without a second site-local Web application
- [x] Bounded gateway read-use audit queue and stream writer, with local
  saturation/failure checks; actual journal persistence/collection is a release gate

Acceptance boundary: implemented protocols, local fixtures, the separately
recorded native candidate probe, and the basic production runtime/three GET
routes, plus real-user lists, expiry/renewal and matched issuance/journal pairs.
One normally issued capability was also explicitly revoked and rejected before
expiry. Positive detail/allocation, membership-policy revocation and audit
delivery/failure acceptance remain open.

The job path stays on-demand. Cache reuse or coalescing should be considered
only when measured load or latency justifies it; a shared collector is not a
required launch dependency. The TUI serializes and coalesces its own reads, but
that does not establish general client/process-wide renewal single-flight.
Interactive reads remain separate from billing exposure/settlement writers;
they do not require a new telemetry batch service.

## Milestone 0.5: packaging and canary

- [x] Shared client package and optional TUI extra
- [x] Package-managed compatibility entrypoint template over one shared runtime
- [x] Full-SHA source/wheel/runtime/node-package manifests, content guards,
  deterministic artifacts and documented rollback procedure
- [x] Bounded native candidate list/allocation reads under the intended service
  UID, using temporary signing inputs and a private audit stream
- [x] Formal basic-job runtime/environment/HTTPS activation
- [x] Actual issuer/user list read, following the basic-job gate above
- [ ] Production canary latency, freshness, journal delivery, failure and
  rollback readback

Basic activation is recorded in the [production connection](site-local-read-plane.md#basic-production-connection).
Further operation enablement and any fleet replacement retain their own gates.
The temporary candidate check does not replace production acceptance.

The shared archive, optional TUI dependency bundle, small login integration
Debian package, full-SHA manifest and canary run card are implemented.
Target install/readback, latency and rollback evidence remain separate
operational acceptance gates; package builds do not prove fleet completion.
