# Terminal workbench design

The workbench helps a researcher choose a readable account scope, find a computation,
inspect its evidence and continue in the console. It uses existing Portal
facts and permissions. A polished screen must also make the current object,
scope, observation time and next action understandable.

## Context and selection

The header gives the current read scope and site, with at most two lines of
context. Use authorized display names in normal selection; keep opaque keys
available for explicit command arguments and technical details. Personal,
organization and project kinds distinguish the authorized names. Compute has
one applied read scope for Current queue and Records and results. Storage and
the default billing identity remain independent; selecting a read scope changes
neither funding nor a working directory.

Self means the current user's native queue across accounts. It has no matching
all-account managed-history reader. Records asks for an explicit named account
in the same selector and never chooses the personal account automatically.
Legacy native account-name/ID arguments remain queue-only until the user picks
a named workspace. Workspace IDs are passed as workspace selectors, never as
Slurm account IDs or inferred native names.

Task scope discovery is a bounded server page. Highlighting a choice is different
from applying it: arrow keys explore, Enter confirms, Escape cancels. Loading
another page must not silently select its first account. Duplicate labels need
visible disambiguation while exact workspace keys remain the selectors. Do not
manufacture a catalog entry from a command-line key or a default identity.

An empty authorized list, an invalid continuation, lost access and a source
failure each have their own explanation and next action. A revoked read scope
must not redirect to another account. Discovery is not a grant; every task and
file read still authorizes independently.

Storage follows the same explicit name-selection interaction with its own
authorized directory. Its source selection stays separate; changing stored or
native source clears the observation while retaining the chosen scope. An
explicit task or storage key resolves its exact authorized name before a data
read. Never walk every page, invent a selectable label from a key, or borrow a
task project's authority to populate the storage selector.

## Information hierarchy

Overview, Resources, Compute and Storage share three presentation phases. Browse gives the main area to
the list or scope discovery. Inspect gives it to the selected object and its
evidence. Summary gives the whole area to Overview or Storage. These phases are
derived from existing view state; they do not own data, permissions or requests.

Use one inspection layout for resources, jobs, allocation, registered location,
managed-task evidence and estimates. Narrow or short terminals hide the list
and its filters during inspection; wider windows may keep a compact list.
The selected object remains visible above the scrollable evidence. Back acts
only on the current view, restores its list and never changes another view's
retained selection. Keep titles readable without letting long names consume
the entire short viewport; full evidence remains reachable by scrolling.

Compute uses one list widget and one selected object. Current queue answers
what the scheduler currently reports; Records and results finds the caller's
accepted computations, including completed records. Switching purpose keeps the
applied scope and returns to that purpose's list. It does not join rows by job
number or claim unrecorded SSH history. The two readers retain their own time,
pagination and authorization semantics. Queue visibility may include authorized
members; managed records remain the caller's own computations.

Task lists emphasize title, state and the last recorded observation. IDs,
complete timestamps and scheduler references belong in details. Native jobs
and managed computations keep distinct source descriptions inside Compute.
Unknown scheduler identity means unconfirmed, not unsubmitted.

At 40 or 60 columns, selecting a task gives its evidence the main area.
Do not keep a tall list above a cramped log. Escape returns to the previous
list page and selection after a fresh authorized read. At wider sizes, retain
a compact list only when enough space remains for useful evidence.

Details, stdout, stderr and output files are modes of the same task. A log or
file view keeps a short task heading instead of repeating all metadata. Paths
wrap fully in the file list; a one-line content heading may abbreviate the path
so the file body stays visible, with the full name retained in the return list. File size and readable time stay separate. Empty, unavailable and
complete pages are different states. Read one bounded page explicitly; no
unbounded scrolling buffer or automatic file polling is required.

Visiting Resources retains the computation selection and reading position;
returning rereads the evidence. View jobs explicitly opens Current queue in
the same applied scope with the selected partition filter. This action does
not carry a stale account choice from a second view. Native-only objects do
not gain output files, final charges or a Run association from that navigation.

## Visual language

Follow the console's restrained teal focus and selection language. A terminal
uses solid backgrounds, weight, spacing and focus states, not simulated Web
shadows or several nested character borders. Ordinary controls remain neutral.
Use green for confirmed completion, amber for attention and red for failure;
queueing, cancellation and unknown state remain neutral. Always pair state
colors with words. Terminal themes must retain readable contrast and a visible
keyboard focus, including monochrome environments.

Show the most useful three or four keyboard actions for the current context.
Text inputs and selectors own their editing keys. The native command palette
provides the complete current action list without creating another command
framework. Visible controls and palette entries invoke the same actions.

Polling is a separate property of that current phase. Frozen allocation,
registration, output/log, resource and estimate inspection stays manual. Do not
offer Pause/Resume there or imply that an immediate refresh enabled polling.
Live job detail and managed task detail retain their existing read behavior.
Footer labels, palette entries and buttons share the same contextual availability;
keyboard editing remains owned by the focused input/selector.

Keep source/freshness distinct from operational feedback. A failed read must
have a visible bounded explanation and a usable refresh/return action instead
of an empty primary area. Empty results must not ask the user to select a row
that does not exist. Unknown values stay unknown, including zero-looking money
or resource counts.

Overview, running estimates and final costs share the same human number format:
group large values, normally round amounts to two decimal places and quantities
to four, and omit trailing zeroes for Credit and quantities. Preserve the sign
and exact necessary digits of values smaller than that display precision; a
nonzero value must not look like zero. This is presentation only. JSON retains
the validated decimal strings, and clients never recompute prices or settlement.

Use one interface language at a time, `zh-CN` or `en-US`. Translate fixed
labels, navigation, states and bounded diagnostics; do not translate user
filenames or provider data. Keep JSON names and machine errors stable. A
translation must not recreate a financial, authorization or state decision.

## Verification

Check the entire journey: discover a project, explicitly select it, inspect a
task and a later page, return to the prior list position, and open the same
task in the console. Include duplicate names, Unicode, unknown values, empty
results, access revocation, delayed responses and an unavailable log.

Review both languages at 100, 60 and 40 columns, including short windows.
Verify the primary evidence is visible, not just that controls stay within
their bounds. Check selection and typing with the keyboard, and inspect actual
rendered screenshots. Local fixtures establish UI and contract behavior;
SSH terminals, long sessions and production latency require separate evidence.

Local PTY checks exercise real terminal input, resize signals, alternate-screen
entry/exit and terminal-mode restoration against a local HTTP fixture. They
complement headless layout checks; they do not establish remote SSH behavior,
terminal-emulator/font coverage or production latency.

The separate [bounded SSH record](docs/ssh-terminal-acceptance.md) establishes
cross-host terminal behaviour for the tested runtime and synthetic workflows.
Keep normal exit, disconnect cleanup, actual backend access, physical terminal
rendering and long-duration resource behaviour as distinct evidence boundaries.

## Reference boundaries

Reviewed 2026-09-24; these are specific interaction references, not a claim of
reusing whole products or their Agent engines:

- [Codex footer source at b7add4d](https://github.com/openai/codex/blob/b7add4df3d95e2d41249e54d3c3a1bd14680848a/codex-rs/tui/src/bottom_pane/footer.rs)
  separates context-driven hints from their width-sensitive rendering.
- [Textual 8.2.8 OptionList source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_option_list.py)
  separates highlight from selection and skips disabled options in navigation.
- [Textual command palette documentation](https://textual.textualize.io/guide/command_palette/)
  describes discoverable contextual commands and fuzzy matching.
- [OpenCode TUI documentation](https://opencode.ai/docs/tui/#sessions)
  describes explicit object selection and command discovery. This reference is
  documentation, not an audit of OpenCode's implementation.

The earlier Claude Code documentation reference remains recorded in
[the terminal workflow](docs/terminal-workbench.md). No upstream reference
supersedes SAI's ownership or read-permission boundaries.
