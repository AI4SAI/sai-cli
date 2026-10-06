# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

Checkmarks cover the implementation or evidence stated on that line. They do
not imply production activation or completion of a paired rollout.

The three-kind managed-read migration preserves personal, organization and
project account selection independently of files and future computation funding.
The [gateway and shared CLI prerequisite](site-local-read-plane.md#three-kind-reader-prerequisite)
was deployed on 2026-10-05; existing-task reads passed with an ordinary user's
Identity login. The original Portal/Pilot owner retains the paired domain,
migration and native plugin work. New personal/organization task acceptance and
the complete product workflow remain open; this prerequisite does not activate
the new domain contract.

## Current product replacement

The previously deployed terminal was rejected as difficult and uninteresting.
Its technical read acceptance remains evidence, not product approval. The
[whole-workbench replacement](workbench-rebuild.md) is deployed with the paired actor-owned work-discovery contract. Existing
ordinary-user result/cost/context and actual SSH/PTY reads passed; whole-product
acceptance remains open. The existing native readers and authorization/billing owners remain.

- [x] Default work discovery without a required account/job/partition form
- [x] Standalone work-to-results shell and actual CLI entry; old shell removed
- [x] Direct result reading/saving, contextual tools and in-workbench device login
- [x] Local paired producer/client reads and rendered navigation checks
- [x] Scoped current native/Run correlation and bounded exact discovery in source
- [x] Paired native gateway/Center correlation delivery and actual native identity bridge
- [ ] Positive current managed-Run correlation and full scientific-work acceptance
- [ ] Pilot-native resource and result continuation, retiring old console links
- [x] Shared replacement CLI and paired Center/site readers selected; Pilot's
  independent browser entry is available through its existing owner
- [ ] First-time and returning-user workflow acceptance in real terminals/Web

Detailed historical checkmarks below describe the stated read capabilities and
release evidence; they do not restore the rejected layout as the target. The
replacement's local test, package, deployment and user-acceptance boundaries
remain separately recorded.

## Basic job reads: deployed, acceptance still open

The formal basic release covers `jobs.list`, `jobs.detail` and `jobs.allocation`.
It is deployed with the bounded acceptance below. The earlier
[candidate record](site-local-read-plane.md#isolated-native-http-acceptance)
used temporary signing inputs; it does not replace the production evidence or
the remaining acceptance gates.

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
- [x] Verify positive detail/allocation on naturally available authorized jobs
  using an ordinary user's account scope, including a non-default organization
- [ ] Complete the remaining Portal consuming-path acceptance
- [x] Correlate actual Center issuance with production journal start/finish pairs
  by capability ID digest, subject, operation and limit
- [ ] Verify audit collection beyond the local journal and production failure handling
- [x] Hold one real capability until expiry: the direct read was rejected,
  then normal issuance restored the read without changing server policy
- [x] Retain gateway package/runtime and configuration rollback materials;
  exercise HTTPS routing and shared-CLI rollback/restoration without static changes
- [x] Restore the complete archived dependency runtime to a fresh prefix,
  reinstall the exact current gateway role, and return to the original runtime.
  An ordinary user's authorized self/account reads and the same small-file
  download passed before, during and after the switch; service invocation logs
  confirmed both restored and returned readers handled requests (2026-10-05).
  Trust/configuration, the execution gateway and shared CLI remained unchanged.
  This does not prove cold-host or credential recovery, external audit delivery,
  or positive allocation when the sampled queues are empty.
- [x] Revoke one normally issued test capability by JTI and reload the existing
  gateway: old lease rejected before expiry, normal acquisition/read succeeds;
  original inputs restored only after expiry. This is not membership revocation
- [x] Exercise a real cached-capability 401 before expiry, exactly one new
  capability issuance, and a successful retry through the installed client
  (2026-10-05). Original revocations and the complete access ACL were restored;
  this is separate from revoking Identity sessions or workspace membership.
- [x] Revoke a separately approved ordinary-user device session using the native
  revocation endpoint (2026-10-06). Its latest successfully rotated refresh token
  was rejected, while the separate daily session refreshed and read successfully.
  The old access token lost issuance permission at its signed expiry; the last
  capability remained usable until its own expiry, then was rejected. Native
  metadata confirmed only the test session disappeared. This does not prove
  membership or shell-access revocation, or instantaneous resource revocation.
- [x] Verify the installed ordinary-user client when its configured read endpoint
  is unreachable: an isolated process network policy produced a network error
  after about 10 seconds, exit code 8 and empty stdout. The observed client made
  one read attempt with no Identity, capability-issuer or broader-source fallback;
  removing the policy restored reading with the same access token and capability
  (2026-10-06). Shared services remained running; this was a client network
  partition, not a whole-service shutdown. Runtime restoration is recorded above.

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
- [x] Identity device authorization/refresh and process-local Identity access token
- [x] Remove HMAC bootstrap, legacy bearer-cache selection and retired auth inputs
- [x] Pair the authentication retirement with Portal's issuer removal in production
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
- [x] Contextual published partition/QOS metadata and comparison; resource
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
- [x] Batch `runs download` for complete binary output, version-bound direct
  ranges, credential separation and atomic non-overwriting local save
- [ ] Paired Center/site release and real-user complete-download acceptance;
  cross-process resume is not implemented
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
- [x] Paired bounded text-content Web/TUI/JSON readers deployed; ordinary-user
  historical text read through the stable shared CLI passed on 2026-10-03
- [x] Paired Web workspace-context migration and one-page resource preparation
  deployed; no-decision relay page removed, task/file reading context retained,
  and financial reads complete independently. Public/service readback passed;
  the authenticated production browser journey remains open
- [x] Task inspection within the workspace and one-action original-history open
  deployed with the text readers; real-browser journey remains separate
- [x] Complete output download for Web/CLI/TUI deployed; an ordinary user retrieved
  an existing file through the stable CLI, with exact hash and no-overwrite readback
- [x] Same-task TUI reading position across evidence modes and catalog navigation,
  published as shared source `4c81f27` on 2026-10-04; ordinary-user candidate and
  selected-runtime reads retained one complete output at 40/60/100 columns.
  This headless TUI check used real APIs; physical terminal and browser acceptance
  remain separate, and the statistics source returned unavailable.
- [ ] Result workflow: authenticated browser retrieval and the complete task journey;
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

The replacement [terminal workbench](terminal-workbench.md) reuses these read
capabilities in one work-to-results journey. The old task-page-to-Pilot handoff
and resource preparation URL remain compatibility consumers pending native
Pilot replacement, not accepted user workflows. Estimate-to-final association,
full resource eligibility, measured GPU utilization and real asset publication
remain unfinished. Native storage reads authorized physical quota subjects,
not an inferred organization pool aggregate.

Acceptance boundary: local HTTP/rendered checks. Prior production reads and
[bounded SSH/PTY runs](ssh-terminal-acceptance.md) do not validate the replacement
layout, terminal font diversity or the user's interest in the product.

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
expiry. Positive detail/allocation and isolated client network failure/recovery
have ordinary-user production evidence. Membership-policy revocation and external
audit delivery/failure acceptance remain open.

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
