# Human and Agent product delivery

Status: established product scope and current delivery map, reviewed 2026-10-11.
The public-distribution and license sections are recommendations, not permission
to publish. [PRODUCT](../PRODUCT.md) remains the product definition; `sai describe`
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
onboarding, not a finished public product. The shipped guide still needs an
operator-supplied wheel and trusted service URL. Deployed `auth login --for`
resolves operation/readback scopes from installed metadata and preserves the old
login until consent succeeds, without changing the profile. Deployed
`configure SERVICE_URL` provides public connection metadata,
standard OIDC discovery and a protected user profile, without manual Identity
fields. CLI `0bc982e47888` and Portal `bc0d9547e947` were paired on 2026-10-11.
The independent base wheel created/rechecked a private profile through actual
HTTPS metadata and Identity discovery. An ordinary user's candidate and selected
shared client also passed existing-session business/native queries and TUI checks.
No new login was started. Independent human first-use and public distribution
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
| Receive and accept a collaboration invitation | Portal invitation lifecycle, original acceptance writer and access-task readback | Paired `invitations list/show/accept` deployed; separate optional scopes | Verify a genuinely requested recipient task, including user consent and applied access |
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

One inherited business effect needs particular care: an organization join that
becomes active selects that organization as the default computing account.
The invitation description, consent and Agent guidance must expose this before
acceptance. Reusing the original writer preserves consistency, but does not by
itself establish that every inherited product rule is desirable. Any change to
this behavior belongs to the shared membership/default-account owner across
consumers, not a compensating CLI write after acceptance.

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

## Proposed open-source distribution

Recommend a public client, public user-operation contracts, generic examples and
tests, and versioned official skills. This lowers adoption and integration cost
while the services retain their own authentication, business policy and data.
Licensing server components is a separate decision. Site-controller artifacts
and patches retain their own provenance and runtime role; a client license must
not silently relabel upstream material.

The [official lark-cli](https://github.com/larksuite/cli) demonstrates a cohesive
product: task shortcuts, typed commands, schema discovery, versioned skill text,
structured output, auth and diagnostics. Reuse those ideas with the current
Python implementation. Its guided setup and permission selection also identify
where SAI's current operator-led first use needs improvement. Mechanical API
code can be generated from intentionally
published user contracts; internal/admin APIs remain with their existing owners.
The Go/npm stack and unrestricted raw-API layer are not prerequisites for SAI.

The repository currently has no approved license. Apache-2.0 is a proposed
permissive option to evaluate alongside copyright/provenance and dependency
obligations; it has not been assigned. No public package, tag, release or visibility
change follows automatically from this document.

Before a publication decision, prepare these concrete outputs:

- A declared license/provenance and bundled-dependency inventory, including
  non-client site artifacts and required notices.
- A reviewed candidate covering current files, reachable Git history, metadata
  and actual package contents; a working-tree pattern scan covers only one part.
- A clean installation and matching official skill with an ordinary-user first
  task on each claimed supported platform; unsupported platforms are explicit.
- Versioning, compatibility, update/rollback, contribution and private security
  reporting instructions, with reproducible validation.

The initial private audit found one operational account name in historical
documentation and an internal host in commit authorship, including a closed
pull request's patch. Current-file checks alone therefore do not justify a
visibility change. A separate private candidate can retain reviewed history
with those identifiers removed; preserve the original private history for
deployment provenance. Do not rewrite the live remote as part of preparation.

The current repository also has an internal self-hosted runner. Public
contributions must use an isolated hosted runner with no SAI network or
credentials. Changing only the workflow label is insufficient while a public
repository can still select the internal runner; remove that access before
publication, or use a clean public repository with no such registration.

[The provenance inventory](../THIRD_PARTY.md) separates the base client, pinned
UI dependencies and GPL-derived scheduler patch. Python source distributions
exclude that patch; the complete repository retains it with upstream notices.
These hygiene changes do not approve the proposed first-party license or a
public release.

## Current order of work

1. Close independent first-use obstacles with the shipped guide and skill on
   supported devices before broadening management again. Prioritize trusted
   configuration delivery, understandable permission selection and recovery;
   preserve existing sessions and do not repeat completed change/restore tests.
2. Verify recipient invitations when there is an actually requested task, through
   the original domain and normal user consent. Keep inviter, budget/storage and
   compute gaps visible; do not manufacture invitations or grants for acceptance.
3. Prepare the remaining public distribution, provenance/history and support
   evidence. Present the audited distribution and license choice before public
   release. Do not wait for 3D or require a Pilot migration for these client tasks.

Digital-twin presentation retains its separate [design](digital-twin-design.md):
authorized asset facts, parameterized models and clear measured/schematic status.
It does not gate a useful local CLI or independent Agent management.
