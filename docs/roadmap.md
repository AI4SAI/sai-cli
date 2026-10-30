# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

Checkmarks cover the implementation or evidence stated on that line. They do
not imply production activation or completion of a paired rollout.

## Current priority: complete human and Agent tasks

- [x] Implement native account discovery, explicit quota directory selection,
  retained query scopes and numbered allocation inspection
  in the portable `0.2.0a1` alpha; see [query usability](terminal-scope.md#query-usability-correction).
- [x] Deploy corrected shared source `d49be4d3ec77` and verify the ordinary-user
  candidate/stable entry, native identity/CPU-ID/directory reads and PTY exit;
  one compute node also passed native reads under the ordinary UID. Configuration
  and profile were preserved. Human visual and fleet acceptance remain separate.

- [x] Deliver shared per-job CPU/GPU allocation facts across CLI/TUI, the gateway
  and Web/Pilot. Shared CLI readability correction `d9695900cd7a` and gateway
  `ead4d38f6d66` are deployed; ordinary-user local/API equality and native TUI
  inspection passed. The corrected view leads with numbered allocations and
  named CPU socket groups; human usability acceptance remains separate.
- [ ] Activate the merged Web/Pilot consumer and updated central relay with
  their original release owner; their source merge is not production acceptance.
- [x] Publish focused-query interaction `053ffffc2ea8`: visible-view polling,
  inline CPU/GPU node inspection and one direct account chooser. Ordinary-user
  candidate/selected reads and terminal restoration passed on a login node;
  human usability acceptance remains separate.
- [x] Publish `node.interconnect/v1` in the shared CLI and read gateway:
  recorded CPU/NUMA↔GPU, GPU↔GPU and node-fabric relationships use one parser.
  Compact default views replace per-thread panels; `i` expands hardware detail.
  Ordinary-user native/API equality and 40/100-column native TUI checks passed.
  See [the deployment boundary](terminal-scope.md#interconnect-correction-2026-10-12).
- [x] Publish the paired native CPU mapping and compact NUMA allocation
  highlights in CLI `8f165a8637db` and gateway `27c312e593b5`. Ordinary-user
  candidate/selected local and API agreement, 40/100-column native TUI and
  terminal restoration passed. Missing mappings remain unknown; Slurm's stable
  daemon start time binds the recorded hardware generation.
- [ ] Complete standard-user multi-node job acceptance and Web/Pilot adoption
  with the existing owner. Unrecorded hardware remains unavailable.
- [x] Publish the job-focused default tree through shared `1bfb4cb18523`:
  ordinary-user candidate/selected queries show the allocated CPU/GPU paths
  directly, with full hardware on expansion. Native views and actual PTY
  restoration passed; data, dependencies and configuration were preserved.
- [x] Publish the shared topology consumer separately from operator capture
  parsing and record construction. CLI `86b76ca8ed65` and gateway `87928eea6866`
  passed existing-record parity and ordinary-user native/API readback. Automated
  collection, publication and expiry alerts belong to the separate operations
  project and are not deployed by this client release.

Follow the [task and delivery map](product-delivery.md). It identifies the
user outcome, existing capability owner, implemented surface and remaining
management gap. Completed commands and tests do not establish complete product
coverage. The records below preserve their evidence boundaries; unchecked
historical entries are not an automatic new-feature queue.

- [x] Finish paired site-discovery activation and ordinary-user installed reads,
  including explicit directory-returned site selection on the base client
- [x] Package portable first-use guidance and an offline official Agent skill;
  a clean installed wheel and independent Agent task passed against synthetic HTTP
- [x] Publish the matching skill on the shared CLI and verify ordinary-user export,
  existing API/native reads and focused TUI entry/exit on 2026-10-11
- [x] Publish `configure SERVICE_URL` and paired public metadata: CLI
  `0bc982e47888`/Center `bc0d9547e947`; independent installed-wheel HTTPS setup
  and ordinary-user existing-session/native compatibility passed
- [ ] Observe independent first-use experience on supported user devices;
  anonymous setup and existing-session checks do not prove a fresh browser grant
- [x] Activate the paired `site.connection/v1` read so a portable client's native
  job/quota queries need only the selected site, with no manual cluster/origin
  configuration. Shared CLI `e93932a6bb46` and Center `cb4f5217791b` were deployed;
  an ordinary user's existing grant verified discovered native job/allocation
  reads while fixed profiles and original authorization remained intact.
- [ ] Deliver the recipient invitation task through the original collaboration
  owner; paired list/detail/accept, shared client and optional scopes are deployed;
  actual new consent, recipient acceptance and site application remain open
- [x] Activate the paired v2 invitation contract and verification recovery through
  shared CLI `922fb8585403` and Portal `3a2ad1b5cba9`. Preview remains read-only;
  verification links and same-invitation readback are shared by human/JSON output.
  Installed-client HTTP recovery passed locally. Ordinary-user production reads,
  existing missing-scope denial and package/configuration checks passed; actual
  new recipient consent, acceptance and site application remain open.
- [x] Publish task-based consent without manual scope/profile editing:
  shared source `7939328519f4`, original metadata/credentials and normal Identity
  consent. Existing-session reads and missing-scope denial passed; actual new
  user consent remains a separate acceptance step
- [x] Prepare the public-alpha client boundary, upstream notices, versioned
  GitHub distribution and Linux qualification
- [x] Publish `v0.2.0a1` with isolated GitHub-hosted Python 3.11/3.13 CI,
  wheel/source/checksum assets, anonymous download verification and clean
  base/TUI installations. This does not update the shared cluster installation
- [ ] Qualify additional supported platforms and independent human first use
- [x] Prepare `0.2.0a2` from a frozen source with current topology, site connection
  and contextual recovery; verify clean Linux installations, upgrade/rollback
  and the shared cluster runtime; see
  [distribution status](product-delivery.md#open-source-distribution).
- [x] Correct the independent `0.2.0a2` review findings: stable selected-site
  routing, matching response filters, contextual pagination, base-to-TUI install
  guidance and readable single-color/narrow-terminal states. Local source
  validation passed 1,272 tests; focused architecture and actual terminal-render
  reviews closed their findings. This is not a production or human acceptance.
- [x] Freeze the final `0.2.0a2` candidate at `b2154b086692`, including PR #14
  corrections and PR #15 job-focused presentation. Final source validation
  passed 1,273 tests and Python 3.11/3.13 CI; the final wheel passed installed
  CLI processes, base-to-TUI installation, PTY restoration and upgrade/rollback.
- [x] Publish `v0.2.0a2` from reviewed `b2154b086692`, verifying the exact tag,
  public page, tagged guide and anonymous downloads of all three assets against
  the approved checksums. Preserve the a1 release and assets. Independent human
  first use and shared production activation remain separate from distribution.
- [x] Activate PR #14 through shared source `4a3d794aee12`: ordinary-user
  candidate/selected native views, existing authorization/account/job/cost reads
  and actual PTY restoration passed; dependencies/configuration were preserved,
  staging and sessions cleaned up. Retain independent human and broader site
  acceptance as separate requirements.

- [ ] Complete paired project-member compute enablement: authorized name/member
  discovery, preview, explicit apply and original request/task readback. Candidate
  source reuses domain guards, locks, idempotency and site receipts; it does not
  add file-role, validity, invite, disable, quota or job-cancellation writes.

Broader budget, storage and compute management remain in the capability map.
Native queries and the first management action are useful foundations, not a
substitute for those domains. Pilot UI and asset-based 3D keep separate ownership.

## Implemented foundations and their validation

Native aliases now use Rich resource tables, native GPU IDX positions, compact
CPU partition groups and the original job/quota columns. Shared publication was
verified under an ordinary UID on a login and a compute node. The identity queue
also includes native child accounts, with a positive organization/project check;
explicit account filters remain exact. This is bounded runtime verification,
not a claim of complete product or human usability acceptance.

The 2026-10-09 user clarification supersedes the earlier summary/cost-only
interpretation. Local SSH-style query convenience and authorized Portal
management are both part of the product. The retired full-screen workbench
does not return. Pilot delivery and hardware assets do not block this work.

- [x] Reconcile product/architecture and inspect the actual shared alias/helper
  chain; this is design and read-only inspection, not local-provider delivery
- [x] Implement `sai jobs local` and versioned `stat_job`/`stat_job_all` wrappers
  over one native Slurm JSON reader; shared activation completed on 2026-10-09
- [x] Bind `sqa`/`ja` to the applied native Slurm account and verify new login
  shells; keep the Unix group namespace separate
- [x] Implement `resources local` and GPU/CPU wrappers over one native observation;
  source support is separate from shared activation and ordinary-user checks
- [x] Deliver GPU/CPU shared helper migration and compact resource presentation;
  ordinary-user login/compute checks completed on 2026-10-09
- [x] Implement local path/project quota reads through native selected fields
- [x] Publish the thin `quota` helper migration and verify ordinary-user local
  reads on a login and compute node, including current directory and explicit path
- [x] Verify local job human/JSON reads without a Portal device session on a
  login node and one compute node; record native call count and sampled latency
- [x] Publish and verify the native `sqa`/`ja` subtree correction with a positive
  organization queue and a leaf-project queue on 2026-10-09
- [x] Deploy the paired organization scope contract across Portal, gateway,
  remote CLI and Pilot; bounded ordinary-user organization/project list,
  detail, allocation, estimate and navigation reads passed on 2026-10-09
- [ ] Complete production membership revocation and the real actor's Pilot
  HTTP/MCP and full browser journeys; local mixed-visibility tests are separate
- [x] Publish offline `sai describe` over the existing command registration;
  source `d7b0a62e97fa` was selected on 2026-10-10. Standard-user no-config/no-native
  discovery and normal-entry TUI checks passed; actual user-device/VM actions remain separate
- [x] Add `sai sites` to discover published IDs/names before explicit selection
  from a portable client, using the existing Portal site chooser
- [x] Publish and verify the paired site-directory route and client on the
  ordinary user's installed path; see [shared delivery](product-delivery.md#shared-first-use-delivery)
- [ ] Verify noninteractive Agent use on a user device and dedicated isolated VM,
  with explicit local/remote prerequisites; the independent Linux-container
  default-account flow below is verified, not the whole device/platform matrix
- [x] Pair normal-user authorization with existing Portal queries and the first
  preference writer and receipt. Broader management remains in the
  [task and delivery map](product-delivery.md#user-tasks-and-capability-owners).
- [x] Implement the default-account source contract: independent write scope,
  expected saved value, existing idempotency/projection records and explicit
  accepted versus applied results; paired Center/CLI/Identity components are
  now deployed, with ordinary-user reads and read-only write denial verified
  on 2026-10-10; the actual change/restore acceptance below followed on 2026-10-11
- [x] Verify ordinary-user consent and permitted same-value management over the
  installed CLI, exact replay, stale-value rejection and read-only write denial
  after normal refresh (2026-10-10); the saved default and old receipt stayed equal
- [x] Verify the complete first management action from an independent Linux
  container: approved account change and restoration, new site receipts and
  native Slurm readback, exact replay, stale-value rejection and isolated-grant
  revocation with a successful fresh daily-session read and write denial

Local job/resource reads and shared helper migrations are deployed. The
[bounded delivery record](terminal-scope.md#local-job-delivery) distinguishes
that evidence from the remaining native helpers and Agent management.

The three-kind managed-read migration preserves personal, organization and
project account selection independently of files and future computation funding.
The [gateway and shared CLI prerequisite](site-local-read-plane.md#three-kind-reader-prerequisite)
was deployed on 2026-10-05; existing-task reads passed with an ordinary user's
Identity login. The original Portal/Pilot owner retains the paired domain,
migration and native plugin work. New personal/organization task acceptance and
the complete product workflow remain open; this prerequisite does not activate
the new domain contract.

## Current terminal correction

- [x] Restore focused Textual interaction after the user rejected the static
  `sai tui` alias. Source `f915ecf0cec0` was deployed once on the shared runtime;
  1105 tests, installed/native PTY and ordinary-user live queries passed.
  Human usability and fleet runtime acceptance remain separate.

The full terminal workbench deployed on 2026-10-06 has been rejected. The
[terminal scope decision](terminal-scope.md) replaces the complete-workflow
brief: native Slurm/Linux remain the normal tools; SAI supplies concise
business context, access, funds/budget and costs. The 2026-10-09 scope also
includes native local query integration and Agent management. Shared Web/Agent contracts
do not require matching TUI screens.

- [x] Correct product scope, presentation rules and cross-interface requirements
- [x] Classify current features against native tools and existing batch commands
- [x] Retire the broad workbench navigation and private view machinery in source;
  the static `sai tui` replacement was rejected on 2026-10-10; restore focused interaction
- [x] No-subcommand entry reuses that same read: terminal text or redirected JSON,
  with no extra UI dependency, native query or automatic login. Local HTTP and
  installed-wheel pipe/PTY checks passed. Shared source `3468ea841490` was selected
  on 2026-10-07 after an ordinary-user candidate read; selected-entry checks passed.
- [x] Verify compact summary, batch contracts and UI removal locally: 917 tests
  passed; package build and public-surface checks passed. This is not
  installed-runtime or human-usability acceptance
- [x] Deliver the reduced runtime through the existing shared publication;
  ordinary-user before/candidate/selected summary reads and direct SSH/PTY
  `sai tui` passed on 2026-10-07. No user-comprehension or interest claim

The existing `sai status` summary is the starting point. Named interaction is
appropriate only when it removes necessary lookup or technical input. No new
dashboard, Portal management pages or Pilot orchestration belongs in the TUI.

The deployed read contracts remain independently useful. Bounded ordinary-user
result/cost/context and SSH/PTY checks passed, but they are not acceptance of
the rejected product. Positive current managed-Run association, native Pilot
workflow and hardware evidence retain their own verification boundaries.
The historical capabilities below do not prescribe terminal features.

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
- [ ] Verify external audit collection and failure handling under the approved
  logging design; local persistent journal evidence is already available
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
- [x] Stop and restore the actual shared read service under a bounded maintenance
  window (2026-10-10). During about six seconds of unavailability, the ordinary
  installed CLI returned HTTP 504, exit 6 and empty stdout. After restart, the
  same cached user credentials and capability read successfully in about 1.15
  seconds; persistent before/after audit pairs retained the same actor and JTI
  digest. Source, protected inputs and the separate execution gateway stayed
  unchanged. This is a bounded service-failure check, not a loaded-fleet SLO.

Use the existing [shared release model](login-node-deployment.md) and the
separately owned gateway role. Asset publication, registered placement, native
storage, Run statistics, GPU telemetry and 3D are independent slices, not
prerequisites for basic job reads. The unified observation implementation keeps
pricing at Center and requires no site price bundle.

- [x] Pair and publish the [unified job-observation implementation](billing-read-plane.md):
  same-observation optional Portal estimates and complete billing/v1 gateway reads;
  later TUI selected-job Cost integration was paired into production on 2026-10-02,
  with the retired UI's evidence kept separate from the batch consumer below.
- [x] Positive full-scope running estimates in an authorized organization,
  including priced and not-started records, before/candidate/selected reads on
  2026-10-07. The compact cost presentation passed real SSH/PTY at 40 columns;
  this does not prove detail-cost or estimate-to-settlement association
- [x] Positive single-job estimate through `sai jobs cost JOB_ID`, shared source
  `5bfe8f74c690` (2026-10-07). An ordinary user's existing running job retained
  its exact execution identity in candidate and selected JSON/40-column PTY
  reads. Final settlement and independent price verification remain separate.

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
and notes, and reuses the existing account overview and permissions.

- [x] Coordinated Portal/CLI overview contract and local role/scope validation
- [x] `sai status` JSON/plain/Rich summary and `sai tui` presentation entry,
  with one shared login fragment; focused Textual interaction is a separate entry
- [x] Shared session and recovery delivery: ordinary-user summary reads,
  automatic renewal on new SSH sessions, scoped rejection, retained TUI context
  and actual PTY exit verified; staging and operator sessions cleaned up
- [ ] Independent user-comprehension and broader site acceptance

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
- [x] Optional job ID reuses the existing exact priced-detail request, with
  independent billing permission and same-observation validation
- [x] Independent `jobs placement`, sharing the
  operator-recorded `jobs.placement/v1` projection with WebUI and Pilot;
  site opt-in, asset review/publication and live acceptance remain separate
- [x] `sai resources catalog` against the shared published site catalog DTO
- [x] `sai storage quota-summary` over Portal
  observations; new storage scope registration is a separate deployment gate
- [x] Explicit `storage native-quota` over authorized
  on-demand Lustre project quota subjects; the actual service UID and temporary
  read-only mount namespace passed a native-adapter preflight on 2026-10-07.
  The exact HTTPS route and formal control-plane mount bindings are deployed;
  one ordinary-user Home quota read and matching issuer/journal pair passed.
  Its isolated device session was revoked and cleaned; managed defaults stayed unchanged
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
- [x] Implement bounded `jobs charges` and exact accounting-record reads over
  Portal's existing final facts, with separate financial scope and redaction
- [x] Publish and live-verify the paired settled-charge reader and shared CLI:
  an existing standard-user session passed self/default/non-default organization,
  exact-record agreement and forbidden-scope checks through the selected runtime.
  Shared configuration and default-account state stayed unchanged.
- [x] Python package metadata and installation entrypoint
- [ ] Shell completion

Acceptance boundary: source compatibility, local integration and the bounded
production user-list/lease checks above. Shared files alone do not establish
production registration, deployed keys or a successful real-user read.

## Shared reads and terminal scope

The former optional-TUI feature checklist is retired. It rewarded reproducing
resource preparation, queues, files, storage, messages and Pilot navigation in
one terminal application. [Terminal scope](terminal-scope.md) determines what
remains; [the prior deployment record](terminal-workbench.md) preserves its behavior
and technical evidence without turning them back into requirements.

Shared capabilities already implemented include authorized Run discovery,
logs, bounded text content, complete binary download, final cost, native step
statistics and exact-Run allocation/registered location. Independent
file/billing authority, pagination, observation quality and protected transport
remain required for their API, batch and Web/Agent consumers.

Relevant acceptance that remains outside this terminal reduction:

- Positive current managed-Run/native association, including execution changes.
- Positive running-step CPU/RSS and the native Web/Agent consuming path.
- Real asset publication, verified physical-device mapping and telemetry.
- Estimate-to-final association under the existing execution/billing owners.
- Pilot-native discovery, resource/result continuation and browser usability.
- Native storage coverage beyond the verified ordinary-user personal scope,
  production failure/load behavior and actual Web/Agent consumers. Formal
  bindings, explicit user consent, one native read and its issuer/journal match
  passed. This remote API does not replace native local quota commands.

Complete text/binary output delivery has bounded ordinary-user evidence,
including a selected-runtime result, exact file readback and no-overwrite
behavior. Shared work discovery and the native identity bridge were paired and
deployed on 2026-10-06. Neither proves a useful TUI or complete scientific work.
Removal of a TUI page does not require an equivalent terminal replacement; a
shared backend can be retired only after its actual consumers are checked.

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
required launch dependency. The compact terminal summary performs one bounded
account read and does not poll native sources.
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
