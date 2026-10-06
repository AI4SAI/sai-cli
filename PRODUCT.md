# Product

## Register

product

## Purpose

SAI helps researchers turn code and data into useful scientific results. The
interface must show what is happening, what needs attention and what can be
used next without asking people to reconstruct scheduler or account internals.
A person should recognize their own work and a useful next action on opening it.
Passing API or layout tests is not evidence that this product is understandable
or worth using.

The current terminal interaction has been rejected and is being replaced. The
[workbench rebuild](docs/workbench-rebuild.md) defines the replacement. Its goal
covers complete work, not another job inspection utility or a collection of
independently correct screens. The existing deployed version remains a
technical baseline until the replacement is verified; it is not the design to
polish or preserve.

## People and situations

Researchers return to ongoing work, investigate a failure, compare results and
start the next calculation. Some use Pilot, some use scripts and many use both.
They may be checking a remote terminal briefly between other research work.
They should not need to learn the platform's object model to get their results.

Project owners additionally need the work and spending they may oversee.
Operators have a separately authorized hardware and fault view. Those roles
change the available facts and actions, not the everyday product vocabulary.

## Product responsibilities

Pilot's native workbench owns the interactive Web computation experience and
retains its full Agent, shell, file, code and workflow capabilities. The TUI is
a terminal entry to the same work and evidence. Portal owns membership, site
access, business policy and final billing. Identity owns authentication.
Native site systems supply dynamic execution and hardware facts.

There is one permission and fact owner for each domain. Clients do not copy
business rules, price jobs, create another task history or infer file access
from a job number. Sharing contracts does not require all traffic to pass
through a single central proxy. The user chooses the site.

## Required everyday experience

- Open into useful work, using established context and authorized discovery.
  Request a human choice only when it changes a meaningful decision.
- Select work by its recognizable name and situation. Internal IDs, scheduler
  state codes, partition strings and source timestamps are secondary evidence.
- Keep progress, relevant logs, available results and costs within that work.
  Looking at a result must not require a model message or a renewed paid window.
- Prefer choices based on known facts over blank text fields. Optional search
  is useful; requiring users to find and paste platform identifiers is not.
- Present the action appropriate to the current situation. Do not display every
  possible action as an equally prominent permanent toolbar.
- Preserve context when returning, refreshing or changing device size. An
  unavailable source or lost permission needs a specific recovery path.
- Show real outputs and real observations. Do not invent scientific progress,
  successful execution, utilization or an association between unrelated facts.

## Interaction and visual direction

Follow the existing SAI identity: calm surfaces, restrained teal focus, readable
contrast and status conveyed with words. Name, state and next action lead;
operational identifiers and diagnostic provenance are disclosed when needed.
Keep ordinary workflows complete with arrow keys and Enter, with discoverable
advanced commands. The user does not have to memorize shortcut letters.

Codex CLI, Claude Code and OpenCode are references for continuous work, focused
interaction and progressive disclosure. They are not permission to fork their
Agent engines or turn read-only work into mandatory chat.

The [terminal design](DESIGN.md) specifies the new interaction. Web styling
remains governed by Portal's existing visual system. No competing brand system
or decorative dashboard is introduced here.

## Acceptance

A first-time researcher must be able to recognize the current site and work,
open an item, understand its state, find an available result and return without
being taught platform terms or entering technical identifiers. An experienced
user must still reach detailed evidence efficiently. Both audiences matter.

Check actual flows in Chinese and English at narrow and wide terminal sizes,
including empty work, failed reads, revoked access, unfinished runs and results
that cannot be previewed. Headless tests, real backend reads, physical-terminal
behavior and the user's assessment are separate evidence. If the user cannot
understand or has no interest in the result, the product goal is still open.

## Digital twin

Hardware views bind real tasks and executions to registered assets and measured
observations under role-based access. TUI, Web and Agent consume the same
structured facts. Parameterized 3D comes from an asset inventory; it does not
own topology or invent utilization. See [the design](docs/digital-twin-design.md).
