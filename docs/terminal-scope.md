# Terminal scope

Decision: the terminal complements native Slurm/Linux work with SAI-specific
information. It does not reproduce Portal or Pilot. This supersedes the
work-to-results rebuild brief and any requirement for TUI/Web feature parity.

The full workbench was deployed on 2026-10-06 and then rejected on product
grounds. Its read/PTY checks remain technical evidence only. Source now removes
that shell: `sai tui` is a presentation entry to the existing `sai status` read,
with no additional read model, polling, keyboard state or automatic navigation.
It prints the summary and returns. Shared source `bdb847a62d79` was selected on
2026-10-07 after an ordinary-user candidate read. The selected runtime passed
Chinese/English reads at 40/60/100 columns and an actual SSH/PTY `sai tui` call
that returned to the shell with exit 0. Its 574 runtime files and permissions
were verified; connection configuration stayed unchanged and the prior release
was retained for rollback. No Center, Identity, Pilot or gateway update was
needed. These are agent-operated technical checks, not human product acceptance.

## Primary need

A researcher working in the shell needs to understand the SAI conditions around
their work: applied account/project, site access, usable funds or budget, cost,
and issues requiring attention. Slurm knows scheduler state; Linux knows files
and process permissions. Neither owns SAI membership, Credit, commercial prices,
project budget or final charges.

When the current Unix/Slurm identity can already read a local fact, use the
native command directly. A queue, file or native quota lookup does not need a
trip through the SAI gateway. That gateway serves authorized remote readers;
testing it with the batch CLI does not make it the normal local workflow.
SAI-specific account, budget and monetary facts keep their control-plane owner.

Plain `sai` reads the existing account summary and returns to the shell. It uses
plain text for a terminal and JSON for redirected output, with no optional UI
dependency or automatic login. Explicit `sai status` keeps its JSON default.
Source `3468ea841490` was selected in the shared runtime on 2026-10-07 after
928 local tests, package checks and installed-wheel HTTP/pipe/PTY validation.
An ordinary user's before, candidate and selected reads retained the same
authorized context. Bare terminal output, redirected JSON and explicit-status
JSON passed against the installed entrypoint, including a 40-column PTY and a
literal `sai` invocation. All 574 runtime files and permissions matched the
artifact; shared configuration and normal login were preserved. Operator staging
and sessions were removed, and the previous runtime remains available for
rollback. This verifies technical behavior, not human product acceptance.

The existing `sai status` and explicit cost commands already answer parts of
this need. Start there. A short status panel returning to the shell is a useful
outcome in itself. Interactive choice earns its place only when it removes a
necessary manual lookup; a general-purpose terminal application does not.

## Feature disposition

| Existing workbench area | Native or existing alternative | Product decision |
| --- | --- | --- |
| Queue, allocation, native statistics | `squeue`, `scontrol`, `sacct`, `sstat` | Remove the general TUI browser. Keep authorized APIs and batch consumers. |
| Logs, files, previews and local saves | `tail`, `less`, editors, native file/transfer tools | Remove the TUI file/log workflow. Preserve managed remote-output contracts and explicit commands where native access is unavailable. |
| Recorded work and task history | Pilot's job plugin and existing `sai runs` commands | Remove the full-work home; do not make Pilot history a prerequisite for terminal use. |
| Applied identity, funds/budget and access issues | Existing `sai status`; native tools lack the business facts | Keep a short read-only summary; use actual server admission facts and bounded notices. |
| Running estimates and settled costs | Existing `sai jobs cost` and `sai runs cost` | Keep explicit, readable cost inquiry. No duplicate queue, new pricing logic or assumed estimate-to-charge join. |
| Project/account selection | Existing authorized discovery, where its scope matches the read | Offer named selection only for a necessary SAI inquiry. Viewing does not switch the shell account or funding. |
| Resource catalogue and comparison | `sinfo` for native availability; `sai resources catalog` for published SAI specifications/prices | Keep explicit catalogue output. Remove the terminal preparation/comparison workflow and mandatory Pilot navigation. |
| Storage | Native quota for filesystem facts; existing SAI quota commands for business observations | Remove the generic storage section. Expose a relevant confirmed limit in a summary only when its exact scope is known. |
| Messages/account administration | Bounded `sai status` notices; Portal for management | Keep short relevant notices and a precise destination, not a terminal inbox or management app. |
| Hardware placement/digital twin | Web hardware view and structured Agent/API reads | No required TUI resource tree, topology or 3D counterpart. |
| Start work / Continue in Pilot | Pilot's own entry and native job plugin | Remove the terminal's workflow orchestration. Any retained link must solve a specific user need. |

These are UI decisions, not a declaration that every listed native command is
available from every host or has identical authorization. Existing machine
contracts, remote reads and independent file/billing permissions remain intact.
Do not wrap native commands inside the SAI client as a replacement backend.

## Delivery order

1. Correct the product brief, design, shared-interface requirements and roadmap.
   Keep deployed behavior visibly separate from the accepted direction.
2. Retire the general workbench navigation and its private view machinery.
   Reuse the compact status presentation and explicit commands; do not replace
   the shell with a smaller dashboard. Any retained interactive choice needs
   an exact authoritative source and a benefit over the existing command.
3. Delete unreferenced UI code and layout-only tests after checking actual
   consumers. Preserve client contracts, safe file transfer, shared presenters
   used outside the workbench, and their meaningful tests.
4. Verify the retained question-to-answer interactions and shared command
   compatibility, then publish through the existing shared-runtime procedure.
   This delivery passed 917 local tests, package checks and installed-wheel
   fake HTTP summary/status/cost reads. Existing ordinary-user account/funds
   reads passed before, on the candidate and after selection. Native/cost self
   lists were empty; they do not establish positive per-job cost acceptance.
   Code landing, installed runtime and human usability remain separate claims.

No new backend service, account store, scheduler wrapper, token type or Portal
screen is needed for this correction. Shared read improvements may continue for
their real Web/Agent consumers. Pilot's native UI and runtime stay with its owner.

## Acceptance

A terminal feature must state what the native tools lack and why the existing
CLI is insufficient. If only the first is true, ship a command or concise output.
If both are true, use the smallest interaction that removes the extra work.

Verify the current context, financial visibility, unknown/unavailable values,
language and narrow/monochrome rendering. Check that the user can return to the
shell immediately and is never forced to browse jobs, files or Pilot to learn
their SAI status. Do not infer job funding, submission permission or directory
ownership from whichever summary happens to be visible.

The wider product still shares permissions and facts. Pilot owns the Web
computing workflow; Portal owns its business domains. Role-based digital twins
and asset-generated parametric 3D remain documented in
[the hardware design](digital-twin-design.md), after trustworthy data.
