# Human and Agent product delivery

Status: established product scope and current delivery map, reviewed 2026-10-14.
Publishing still requires the maintainer release process. [PRODUCT](../PRODUCT.md) remains the product definition; `sai describe`
remains the executable operation catalogue.

## Product decisions

| Perspective | Decision | Evidence of value |
| --- | --- | --- |
| Business | Make the client an accessible entry to SAI computing services and research workflows; retain the user's choice of site and Agent | Independent adoption and repeated useful tasks |
| Operations | Maintain one client, one shared cluster publication and a supported portable installation | Fewer support interventions; reliable upgrades and recovery |
| Product | Preserve fast native habits for people and complete authorized tasks for Agents | Less typing and context switching; understandable results and failures |
| Architecture | Keep each fact, permission and action with its existing owner | Shared contracts without duplicate business state or cross-product runtime dependencies |

Measure these through bounded user journeys before adding telemetry machinery.
The open client can reduce integration cost; adoption or revenue growth is a
product hypothesis to validate, not a result established by publishing source.

The current judgment is a useful internal client with incomplete independent
onboarding, not a mature product. Versioned GitHub releases provide the reviewed wheel;
a user still selects their trusted service URL. Deployed `auth login --for`
resolves operation/readback scopes from installed metadata and preserves the old
login until consent succeeds, without changing the profile. Deployed
`configure SERVICE_URL` provides public connection metadata,
standard OIDC discovery and a protected user profile, without manual Identity
fields. CLI `0bc982e47888` and Portal `bc0d9547e947` were paired on 2026-10-11.
The independent base wheel created/rechecked a private profile through actual
HTTPS metadata and Identity discovery. An ordinary user's candidate and selected
shared client also passed existing-session business/native queries and TUI checks.
No new login was started. Independent human first-use and broader platform qualification
remain open; existing-session checks do not establish a fresh browser grant.
Linux acceptance also does not establish Windows or macOS support.

The next acceptance must use the installed client and shipped guidance, without
an operator supplying missing commands, technical IDs or recovery steps along
the way. Record task completion, manual inputs and interventions, including
normal permission denial. Existing native query and management receipts remain
valid; do not recreate a VM or repeat an account change to produce more evidence
for an already completed action.

## User tasks and capability owners

| User task | Existing owner and path | CLI evidence today | Remaining product work |
| --- | --- | --- | --- |
| Check local queue, GPU/CPU allocation and path quota | Native Slurm/Linux/Lustre under the actual Unix user | Shared aliases and focused Textual queries deployed; ordinary login/compute checks | Preserve familiar output and latency; broaden real terminal/device usability evidence as needed |
| Start on a user device and choose context | Identity device flow; Portal site metadata and account policy | [First-use guide](getting-started.md), bundled skill and synthetic independent-Agent workflow verified; shared site discovery and account choices deployed with ordinary-user reads | Observe independent first-use experience on supported devices using shipped guidance |
| Understand work, results and costs | Native/site job observations, existing managed Run reads, Portal final billing | Job/Run reads and output download; running estimates and settled charges have distinct contracts | Verify complete user tasks across the supported contexts; do not equate one list or sample with all workflows |
| Change the default computing identity | Existing Portal preference writer and site projection receipts | Actual ordinary-user change, restoration, replay and independent-session cleanup verified | Preserve accepted/applied distinction; broaden supported-device evidence without repeating a no-op mutation |
| Receive and accept a collaboration invitation | Portal invitation lifecycle, original acceptance writer and access-task readback | Original workflow deployed; v2 explicit permissions and preview/`--apply` need paired activation | Verify a genuinely requested recipient task, including user consent and applied access |
| Invite and manage collaborators | Portal collaboration resource resolver, invitation/change services and site-state readback | No inviter-side OAuth CLI management adapter | Resolve named context/recipient, show permitted roles and expiry, submit through original owner, follow invitation and applied site state |
| Manage a project's budget | Portal project-budget service, role checks and budget events | No CLI management adapter; cost/overview reads are not this action | Design authorized request, concurrency/replay and exact readback against the existing writer before exposing a write command |
| Manage storage allocations or compute lifecycle remotely | Existing Portal storage and compute domain services and task receipts | Storage and computation read surfaces exist; broad management is not delivered | Pair each useful user intent with its current authority and durable outcome; native read visibility does not imply remote write rights |

The collaboration route family currently uses browser admission. Its existing
`resolve_collaboration_resource`, `invite_workspace_collaborator` and
`change_workspace_collaborator` services are the intended reuse points, not an
invitation to forward browser credentials from an Agent. Likewise, the budget
writer `set_project_budget` already owns locks, amount constraints and request
references; an Agent adapter must inspect its actual replay/concurrency semantics
rather than assume that a request ID supplies every required guarantee.

The current management slice covers the recipient's complete invitation task,
shared by organizations, projects and directories. It reuses the existing
invitation and task owners. Inviter-side collaboration remains a candidate for
broader management: inspect people, resolve an intended recipient, select role
and validity, submit through the original owner and inspect application. Its
priority still needs comparison with recurring user needs and the other gaps;
available endpoints alone are not a reason to expand the surface.

An organization join preserves an existing valid default computing account;
Portal selects the new organization only when no valid default exists. This
global choice is independent of the new site's association delivery. Invitation
copy and Agent guidance follow the shared membership/default-account owner;
the CLI never issues a compensating preference write after acceptance.

## A useful first release

The public alpha should support three understandable journeys:

1. A cluster user runs familiar native queries immediately, without a Portal
   login, then requests SAI business context only when needed.
2. A user installs the portable client, signs in normally, discovers operations
   and context, and obtains a useful authorized result using shipped guidance.
3. An independently chosen Agent completes one explicitly requested management
   task, reports acceptance separately from application, and handles a retry or
   refusal using the same business contract.

Evaluate these with the installed artifact and documented instructions. An
operator who supplies missing URLs, IDs and internal knowledge throughout the
test has not proved independent usability. The earlier isolated Linux management
acceptance is valuable evidence for its exact action, not every client platform
or the entire Agent product. More business coverage remains required after alpha.

Measure successful completion, first-use steps, technical values the user must
type, recovery effort and operator intervention. Preserve native query latency
against its original baseline. Treat authentication/session continuity, normal
permission denial and upgrade recovery as part of the journey.

## Human presentation and Agent integration

Human output emphasizes the result and useful next action. Preserve the native
helper's GPU positions, compact CPU groups and readable job/quota columns.
Focused interaction belongs where choosing removes typing or repeated lookup.
Authorized CLI management does not require matching administration pages in the
TUI; people can use those same explicit commands or their preferred Agent.

Agents use the same typed operations, stable JSON/errors, parameter/effect/scope
metadata and domain receipts. Extend the existing `describe` owner when result
contracts or examples are needed. Official skills should be short task guidance
bound to the matching CLI version, with detailed syntax obtained from the CLI.
They must not contain another manually maintained permission or command registry.

The base wheel now provides `sai skill`, with JSON or exportable Markdown.
An independent Agent used only its bundled guidance and installed operation
descriptions to resolve synthetic site/account names, perform one requested
global preference change and distinguish old, pending and applied receipts.
Fresh installation and device authorization were also exercised against local
HTTP fixtures. This is client/workflow evidence, not real consent or a production
release. The guide and skill require no additional runtime dependencies.

Shared client `594ef8089fad`, published on 2026-10-13, adds matching local/remote
allocation explanations and a hardware-query task in the bundled skill.
An ordinary user verified the installed descriptions, skill export and one
existing job's native CPU mapping/GPU indices before and after selection.
The 964-file runtime, unchanged dependencies/configuration, 1217 tests and
Python 3.11/3.13 CI passed. Staging and sessions were cleaned up; rollback remains.
This is bounded batch-client evidence, not independent Agent decision-making or
Web/Pilot interconnect adoption.

## Shared first-use delivery

On 2026-10-11, shared CLI source `9a51836dc880` was selected after the existing
service owner's compatible Center release. The immutable runtime's 950 files
and public permissions matched the reviewed artifact. Configuration and shared
login-profile bytes stayed unchanged; the previous runtime remains available
for conditional rollback. No node-local package or service restart was needed.

An ordinary user's existing device session passed candidate and selected-entry
reads of site names, account choices, published resources and settled charges.
The base client explicitly selected the directory-returned site using the same
trusted non-secret profile. Native jobs/resources/Lustre quota and the focused
GPU TUI passed, including exit and terminal restoration. The current self job
and estimate scopes were empty; these reads do not prove positive job execution.

The skill export matched the previously exercised bytes. Temporary staging and
all operator sessions were closed. This completes the paired site-discovery and
shared skill publication, without new consent or business writes. These checks
ran on a login host: fresh independent-device onboarding, whole-product human
usability and broader management remain separate acceptance work.

On 2026-10-11, shared source `7939328519f4` added task-based consent and the
recipient invitation commands. The native Identity deployment added only two
consent messages and optional scope definitions; other providers and protected
configuration remained unchanged. The newer Center release already included
the matching API, so it was preserved. Both candidate and selected entry passed
ordinary-user existing-session reads, missing-invitation-scope refusal, native
queries and GPU TUI entry/exit. Shared profile/configuration and previous runtimes
were retained; staging and all operator sessions were closed. No new user grant,
invitation acceptance or business mutation was performed. This establishes
publication and existing-session compatibility, not completed recipient consent
or general usability.

Keep three extension points concrete: native readers, business-operation modules
and Agent skills. A dynamic plugin framework needs real external consumers before
it becomes a supported platform. Pilot plugins consume shared capabilities;
they do not become a runtime requirement for another Agent.

## Open-source distribution

The first-party client, user-operation contracts, generic examples/tests and
versioned official Agent guidance use Apache-2.0. The shared native projection
is included; other Portal/Identity/Pilot server code is not licensed by this
repository. [Third-party provenance](../THIRD_PARTY.md) records optional UI
licenses and the separately licensed Slurm patch.

Versioned GitHub releases provide a wheel, source distribution and SHA-256
checksums from one reviewed source commit. The initial public version is
`0.2.0a1`; the preceding `0.1.0` deployments were internal. A wheel upgrade does
not alter credentials or grant permissions. Retain the prior artifact for
rollback. Pre-release versions and incomplete platform support must remain
explicit in instructions and release notes. No PyPI registration is claimed.

The [first public alpha](https://github.com/AI4SAI/sai-cli/releases/tag/v0.2.0a1)
was published on 2026-10-12 from `cb42d6987b95c870071915166554b7017eae5bc4`.
The independent public repository is the active development source; the original
history remains in a private read-only archive. GitHub-hosted Python 3.11/3.13
CI passed 1200 tests and packaging checks without internal runners or secrets.
Anonymous downloads matched all three published asset hashes. Clean Linux pipx
base/TUI installs exposed the matching skill and 39 operations, verified public
connection metadata and reported missing login normally. No new device consent,
business mutation or shared-site installation was performed by this release.

The revised `0.2.0a2` candidate includes recorded interconnects, CPU locality and
selected-site connection discovery. Independent product, delivery, architecture
and visual review led to correction `f08b38702639`, merged in PR #14. It keeps
portable routing stable when adding a cluster constraint, binds returned job
and estimate rows to the requested filters, and preserves connection context
when paging. First-use guidance, adding TUI to a base install, resolved account
selection and narrow/single-color terminal states were also corrected.

The corrected source passed 1272 tests and GitHub-hosted Python 3.11/3.13 CI.
Frozen packages passed provenance, content and disclosure checks. Independent
Linux pipx installation exercised configure, synthetic login/consent/resume,
selected-site reads and invitation paging through actual CLI processes.
Adding TUI with the documented command, entering/exiting a real PTY and a1
upgrade/rollback preserved the configuration. Architecture review checked the
existing policy/grant/consumer chain; visual review checked actual rendered
Chinese/English actions and states at 40/100 columns. These checks do not prove
new human browser consent, production activation or complete product usability.
Public tag/release publication still requires maintainer authorization; the a1
assets remain unchanged. Release provenance must identify the exact final commit
and artifact hashes, rather than treating the earlier candidate as current.

Shared runtime `4a3d794aee12` was selected on 2026-10-14. An ordinary user passed
candidate and selected-entry CPU/GPU views at 40/100 columns, an
existing job's bilingual topology/resize controls, six authorized account choices,
remote job list/detail/allocation/interconnect and non-final cost reads. A real
PTY exited normally and restored terminal settings. One job timed out between
the running list and detail requests; the native observation confirmed that
transition, and a fresh bounded query completed against a current running job.
No client fallback or scope relaxation was used. All 964 runtime files and permissions
matched the inventory; dependencies, configuration, login profile and existing
authorization were preserved. Staging and operator sessions were cleaned up;
the previous `5c5066a7475f` release and rollback inputs remain, without a rollback
drill in this window. This does not establish
independent human first-use or multi-site acceptance.

The later presentation refinement `1bfb4cb18523` is also deployed through the
shared runtime. Ordinary-user native checks show a small job's CPU/GPU placement
and GPU connection directly on the first narrow screen, with full hardware on
expansion. This adds no read or JSON change.
See [the topology delivery boundary](terminal-scope.md#interconnect-correction-2026-10-12).

The final `0.2.0a2` release is frozen at
`b2154b0866923f90f627038977790017d496b6bd`, including both PR #14 and the PR #15
job-focused presentation. Its runtime files match the deployed `1bfb4cb18523`
source. The final source passed 1,273 tests and Python 3.11/3.13 CI; the final
wheel passed independent Linux installation, synthetic authorization/recovery,
TUI installation, PTY restoration and upgrade/rollback checks.

The [a2 prerelease](https://github.com/AI4SAI/sai-cli/releases/tag/v0.2.0a2)
was published on 2026-10-14. Its tag points to that exact source; anonymous
downloads of the wheel, source distribution and checksum file matched the
reviewed artifacts. The public release page and tagged first-use guide were
also verified without a login. The a1 release and assets were preserved.
This GitHub publication did not change the shared installation or publish to
PyPI. Later documentation updates do not change the frozen source or artifacts.

API schema versions are independent of the client release version. Additive
server fields remain ignored until modeled; incompatible contracts need paired
consumer/producer changes. The installed `describe` output owns command syntax.
Native reads remain independent of control-plane connectivity.

Public pull requests run on isolated hosted CI without SAI credentials, private
network access or internal runner registration. Use GitHub private vulnerability
reporting for sensitive findings. Keep production evidence and private account,
host and asset identifiers outside this public repository and its issue reports.

The [official lark-cli](https://github.com/larksuite/cli) demonstrates useful
operation discovery, task-oriented authorization and versioned skills. Reuse
those product ideas without introducing a CLI-owned model loop or another
business state store. Native readers, existing business operations and Agent
skills are the current extension points; a generic plugin framework needs real
consumers before it becomes a supported platform.

## Current order of work

Selected-site connection discovery was paired and deployed on 2026-10-13:
CLI `e93932a6bb46`, Center `cb4f5217791b`. An ordinary user's temporary connection
profile omitted site, cluster and gateway settings; explicit site selection
resolved the latter two and read the organization queue and an existing job's
allocation/interconnect, matching the local native observation. The same check
passed before and after shared runtime selection. The existing grant and profile
were preserved, and the terminal restored normally on exit. Source coverage
also includes independent site origins and the quota/cost paths; this live check
does not establish independent-device onboarding, fresh browser consent or
another production site's ingress. The prior programs/configuration remain
rollback inputs; remote staging and all operator sessions were cleaned up.

1. Close independent first-use obstacles with the shipped guide and skill on
   supported devices before broadening management again. Prioritize trusted
   configuration delivery, understandable permission selection and recovery;
   preserve existing sessions and do not repeat completed change/restore tests.
2. Verify recipient invitations when there is an actually requested task, through
   the original domain and normal user consent. Keep inviter, budget/storage and
   compute gaps visible; do not manufacture invitations or grants for acceptance.
3. Keep versioned distribution, provenance/history and support evidence current.
   Review release artifacts and compatibility before each public release. Do not wait for 3D or require a Pilot migration for these client tasks.

Digital-twin presentation retains its separate [design](digital-twin-design.md):
authorized asset facts, parameterized models and clear measured/schematic status.
It does not gate a useful local CLI or independent Agent management.
