# Terminal workbench design

The workbench helps a researcher choose a readable project, find a computation,
inspect its evidence and continue in the console. It uses existing Portal
facts and permissions. A polished screen must also make the current object,
scope, observation time and next action understandable.

## Context and selection

The header gives the current project and site, with at most two lines of
context. Use authorized display names in normal selection; keep opaque keys
available for explicit command arguments and technical details. The task
project, native job scope, storage workspace and default billing identity are
independent. Selecting one never silently changes another.

Project discovery is a bounded server page. Highlighting a choice is different
from applying it: arrow keys explore, Enter confirms, Escape cancels. Loading
another page must not silently select its first project. Duplicate labels need
visible disambiguation while exact workspace keys remain the selectors. Do not
manufacture a catalog entry from a command-line key or a default identity.

An empty authorized list, an invalid continuation, lost access and a source
failure each have their own explanation and next action. A revoked project
must not redirect to another project. Discovery is not a grant; every task and
file read still authorizes independently.

## Information hierarchy

Task lists emphasize title, state and the last recorded observation. IDs,
complete timestamps and scheduler references belong in details. Native jobs
and managed computations keep distinct labels and source descriptions.
Unknown scheduler identity means unconfirmed, not unsubmitted.

At 40 or 60 columns, selecting a task gives its evidence the main area.
Do not keep a tall list above a cramped log. Escape returns to the previous
list page and selection after a fresh authorized read. At wider sizes, retain
a compact list only when enough space remains for useful evidence.

Details, stdout, stderr and output files are modes of the same task. A log or
file view keeps a short task heading instead of repeating all metadata. Paths
wrap fully; file size and readable time stay separate. Empty, unavailable and
complete pages are different states. Read one bounded page explicitly; no
unbounded scrolling buffer or automatic file polling is required.

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
