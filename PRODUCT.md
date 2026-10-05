# Product

## Register

product

## Users

SAI scientific-computing users work from terminals, the SAI console, and hosted
Agents. Researchers need to choose resources, understand running work, inspect
results and costs, and continue the same task across these entry points.
Project owners review their authorized work and budgets. Operators have a
separately authorized view of hardware, networks and failures.

## Product Purpose

Researchers come to complete scientific work, resume it, diagnose failures and
obtain results. Resource selection, execution, files and costs are supporting
capabilities, not a mandatory sequence of pages. The same researcher may use
Pilot, native scripts or terminals for different work. Pilot's existing compute
plugin is the interactive Web workbench; the console owns account and financial
management rather than a parallel daily compute workflow.
Account/project context changes the authorized scope, not where users look for
their computations. Job and managed-Run records must not become competing product
menus, and a runtime pool must not be presented as a scientific task or workspace.

The implemented product is a read-only compute CLI with an optional terminal
workbench for resource comparison, job allocation and operator-recorded
locations, managed task history, logs, output listings, storage quota and
running estimates. Authorized job
context can continue into the console and its existing Pilot flow.
The terminal design rules live in [DESIGN.md](DESIGN.md); language, context
selection and evidence layout are part of the task workflow, not a separate
decorative layer.
Result inspection and retrieval are core workbench outcomes. Returning to a
Pilot conversation with a file reference is an optional aid to further work;
it does not establish that the user can inspect, obtain or interpret the result.
Bounded task-output text reading is implemented in paired source for Web, TUI
and JSON. Paired inspection and complete output download are deployed, with bounded ordinary-user
CLI verification. The authenticated browser journey and useful follow-up analysis
leave the broader product acceptance open.
It shares Portal-owned read contracts with WebUI and SAI Pilot. The broader
workbench design, including hardware telemetry and result navigation, is described in
[the unified workbench design](docs/unified-workbench.md); the design is not an
implementation or deployment claim.

Bilingual navigation, readable compute/storage discovery and narrow task inspection
are implemented. Four top-level views share browse, inspect and summary layouts;
Compute uses one scope and selected object across queue and records/results purposes.
Contextual actions follow the terminal visual rules in DESIGN.md.
[Bounded SSH acceptance](docs/ssh-terminal-acceptance.md) covers a 14-minute
synthetic workflow on one login host, resize and disconnect cleanup. Broader
terminal/font coverage, longer resource profiling and production backend
acceptance remain open. Interaction references inform selection, keyboard and
action discovery; they do not imply reuse of another product's application or
Agent source. Keep the task journey ahead of a broad redesign.

## Brand Personality

Precise, calm, capable. Follow the SAI console's product language and existing
visual system; do not define a competing WebUI theme in this repository.

## Anti-references

- A terminal job table presented as a complete workbench.
- Decorative hardware scenes with invented utilization or placement.
- Independent business rules or task histories for each client.
- A restricted chatbot replacing the full SAI Pilot Agent experience.
- Portal pages owning a second Pilot Session/Pool workflow instead of a thin
  integration with the native workbench and its SAI plugin.
- Rebuilding the compute plugin as a second Portal job/task workbench.
- Internal protocol terms, raw errors or credentials in ordinary user flows.

## Design Principles

- Keep workspace, site, billing identity and file access explicit and distinct.
- Show resource choice, execution, evidence and results as one task journey.
- Reuse authoritative services; render the same facts appropriately per client.
- Let Agents read typed data directly with the caller's actual permissions.
- Keep allocation, measured utilization, predictions and final charges distinct.
- Keep operator registrations distinct from proof of the current machine;
  disclose only authorized job-node locations, never infer empty cabinet space.
- Preserve full Agent capability inside the authorized execution boundary.

## Accessibility & Inclusion

Provide complete keyboard navigation, readable contrast, non-color status cues,
Chinese and English catalogs, terminal resize handling and reduced motion.
The Web target is WCAG 2.2 AA. Hardware information must remain usable through
semantic tables and trees without a 3D renderer.
