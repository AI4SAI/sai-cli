# Workbench rebuild

Status: replacement design and implementation brief, not an accepted or deployed
product. This replaces the old terminal's scope-first forms, parallel queue/run
navigation and permanent technical toolbars.

## What the researcher gets

Opening SAI should make ongoing work, a problem requiring attention or an
available result recognizable immediately. Returning users continue from their
work, not from an infrastructure setup form. A new user sees a concrete way to
begin useful work through Pilot; simply displaying a resource catalog or an
empty job table does not satisfy that outcome.

The product earns interest by removing work: finding context, monitoring an
execution, locating evidence and retrieving a result. Decoration, shortcut
counts, a 3D scene and a list of implemented endpoints are not substitutes.

## Three continuous states

| State | Primary content and action | Secondary content |
| --- | --- | --- |
| My work | Recognizable work names, current situation and useful recent changes; select work or continue it | One site/context switch and optional name search |
| This work | State and relevant evidence; inspect a problem or open available results | Resources, costs, detailed identity and provenance |
| Results | Actual files; read or save the selected result and return to the same work | Continue analysis in the appropriate Pilot context |

Wide terminals may keep the work list beside the selected work. Narrow terminals
show one level at a time. Opening details, a log or a file must not spawn another
product window. Resource and storage views are contextual tools for preparing
work or diagnosing a specific issue. Account and financial management retain
their existing Portal owner.

No technical text input is required for opening the product, finding known
work, selecting a state/resource filter, inspecting it or opening an existing
result. Names are chosen from authorized data. Optional search, scientific
instructions and a user-chosen local save path are intentional user input.
The explicit job number remains an advanced diagnostic capability, not the
primary solution to finding work in a large list.

## Context and facts

Known server context removes repeated setup; it does not confer extra rights.
`account.overview/v1.context` can preselect a currently resolved account. Every
work read still authorizes. Its absence cannot hide read-only collaborations,
and a default billing account is not a universal read filter.

The target home covers the caller's work at the explicitly selected site.
The candidate now provides native self queue observations and an actor-owned
Run page across currently readable workspaces. The paired read is locally
verified and not yet deployed. The terminal does not walk projects. This closes
work discovery in source, not native Job/Run association or product acceptance.

The minimal shared addition is an actor-bound, site-bound, paginated Run read
across currently readable workspaces, including server-owned workspace labels.
Reuse the current readable-workspace relation, Run owner filter, item projection
and accepted-time/reference cursor. No new task table, authorization store,
service or migration is needed. A new DTO is required because the existing
`compute.runs/v1` contract is explicitly single-workspace.

Native self reads retain their authorized site-local path and their own time
and completeness. History pagination and a live queue are not one frozen
snapshot. A current Job and a Run can be treated as one work item only when the
existing execution-binding authority supplies sufficient evidence. Number-only
joins, guessed account mappings and per-Run native probes over an entire list
are not an acceptable substitute. The candidate now groups unique current evidence with the
[shared correlation contract](../contracts/managed-run-link/v1/README.md),
including bounded exact discovery outside recent history. Paired deployment
and real-work acceptance remain open; permanent accounting identity and file
access remain independent.

Pure native work does not have managed output permissions merely because it
appears beside a Run. Missing logs, declared results or final-cost attribution
remain real capability gaps. No invented files, success or progress percentage.

## Implementation ownership

- Portal compute-read owns actor/workspace/site filtering, labels, pagination
  and recorded Run projections. Existing billing owns settled facts.
- Site-native readers own live scheduler observations and execution evidence.
- CLI owns allowlisted read models and terminal interaction, using the same
  narrow request paths available to other consumers.
- Pilot owns native sessions, work directories, Agent execution and Web work.
  Its in-progress directory/first-session correction stays with that owner.
  Agent reads remain bound to the current granted scope, not implicitly enlarged
  to every account a human UI can browse.
- The shared workflow contract coordinates these consumers. It is not another
  framework or a reason to put Pilot orchestration back in Portal pages.

## Replacement sequence

1. Freeze this user workflow and the minimal shared work-list contract. Identify
   the authoritative execution association and the native-result gaps explicitly.
2. Implement and pair the missing read contract; negative membership, site and
   cursor checks belong at its existing owner. Keep the current DTOs intact.
3. Replace the terminal shell and its old control layout as a whole. Reuse
   proven transport, authorization, typed observations and safe result reads.
   Retire old view-state machinery and tests that only enforce the removed layout.
4. Connect entry, work, results and continuation in a real interactive flow.
   Pilot-native continuation is paired with its owner; ordinary reads never
   create a model window or submit a job.
5. Review default, empty, running, failed, completed, unavailable and revoked
   states through the user's tasks. Validate Chinese/English, narrow/wide views,
   actual backend reads and physical-terminal behavior separately. Deploy the
   paired result, then obtain user assessment of clarity and usefulness.

The objective remains open until the whole workflow is understandable and useful.
Completing the read contract, a new screen or a release is not sufficient.
Hardware task/allocation/asset/telemetry association and the role-based digital
twin remain part of the full product. Parameterized 3D follows truthful data as
specified in [the digital-twin design](digital-twin-design.md).
