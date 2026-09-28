# Terminal workbench

Status: implemented read-only client. Source tests cover interaction and HTTP;
deployment coverage and real-user acceptance are recorded separately.

Install the optional extra and use the existing connection configuration:

```bash
python3 -m pip install '.[tui]'
sai tui
sai tui --language en-US
sai tui --site site-a --scope project-account --account project-example
```

An interactive terminal is required. Scripts should continue using the JSON
commands. Managed login-node connection settings retain their existing owner
and override restrictions. Installing the extra locally does not deploy a
shared login-node package or gateway.

## A useful first workflow

The workbench starts with Overview: identity, authorized funds and unread
messages. On managed nodes it retains the applied login Account; Jobs and
Storage keep their independent, explicitly selected scopes.

1. Open Resources and press Enter on one or two partitions. Compare CPU/GPU
   model, per-node CPU cores, total GPUs, nodes, QOS and published prices in
   the detail panel. Unknown facts remain unknown; no availability or price
   calculation is inferred.
2. Use View jobs to apply the most recently selected partition to the Jobs
   view. Change scope, account name/ID, partition or states and select Apply.
   The applied context remains visible; draft controls do not change authority.
3. Press Enter on a job or choose Details for its separately authorized
   detail. Allocation instead requests one allocation snapshot from the
   explicitly configured site gateway. Escape returns to the list. Ordinary
   detail uses native site-read mode when configured and the existing Portal
   transport otherwise. Allocation requires native configuration and capability
   mode; missing configuration displays an error. Neither path falls back.
4. Open Running estimates to request the independent billing DTO. Enter shows
   one item's amounts, price revision, source time and uncertainty. This is
   never a final charge. No match to a job is guessed from its numeric ID.

Allocation inspection takes job identity, scheduler states, restart count,
observation time/freshness and node CPU/memory rows from one response. It never
combines an earlier job detail with a newer node list. `allocated`,
`not_allocated` and `unavailable` remain distinct; unknown memory remains unknown.
Array tasks retain their complete identity, including task zero (`12345_0`),
for both detail and allocation requests. The v2 response includes bounded node
GRES entries when native evidence can be bound to the node: resource name/type,
allocated quantity and optional Slurm-local indices. Shared quantities retain
their own units. Missing evidence stays unknown; these values do not establish
physical GPU placement, MIG parent identity, measured utilization, racks or topology.

Storage rows in Resources are published products only, not quota usage or
file access. The separate Storage tab selects a stored quota sample or an
on-demand native Lustre quota query after an
explicit workspace key and Load; job account/scope never select that workspace.
`sai tui --storage-workspace-key org:example` preselects it. Editing the workspace
clears previous data immediately; Load and every refresh reauthorize the read.
`sai.storage.read` is required. State, effective versus target quotas, nullable
usage and observation time remain distinct; a negative remaining value means
the observed usage exceeds the effective quota. Native mode instead shows exact
byte/inode counters from authorized physical quota subjects. Native zero limits
mean unlimited; rows are not a whole organization pool total. It requires the
configured site gateway and never falls back to stored data. Changing source
clears old results immediately and discards late responses from the previous
source, using the same serialized reader.

The workbench does not add placeholders for unavailable native result preview,
settled billing or hardware telemetry features.

## Interaction and data behavior

- F5 or Refresh requests an update. F6 pauses/resumes automatic refresh;
  Ctrl+Q exits. Tab and arrow keys use standard Textual focus/navigation.
- The active view refreshes every ten seconds; inactive views do not poll.
  Inspecting an estimate pauses that view's automatic refresh to preserve its
  exact snapshot. Escape or a manual refresh leaves that inspection.
- Inspecting an allocation also pauses automatic refresh. F5 or Refresh clears
  the old allocation immediately and requests a complete replacement snapshot;
  inspection remains paused. Changing job, detail/allocation mode, applied scope
  or tab, or pressing Escape, discards the allocation and any late response.
- One background reader serializes client calls, including credential refresh.
  Repeated requests coalesce into the latest requested view/context. Changing
  scope clears old data and invalidates in-flight results. Network calls are
  still bounded by the existing HTTP timeout, not physically aborted.
- Authentication failure clears all cached display data and pauses polling.
  A permission or source error clears only the affected view; fee access does
  not imply job access or vice versa. Errors use the client-safe diagnostic.
  Failed views wait for manual refresh or re-entry rather than polling the
  same error indefinitely.
- Jobs retain the requested server limit and show truncation where the DTO
  supplies it. Estimates are a complete authorized server snapshot displayed
  in local pages of 100 rows. These pages do not claim server pagination or
  live atomicity across multiple requests.
- Backend text is rendered literally; Rich markup or terminal controls cannot
  become instructions to the display. Ordinary catalog prose may wrap.
- Narrow/short windows use compact controls; details scroll vertically and
  tables can scroll horizontally. Comparison remains a table of the same
  validated facts, not a new product or pricing model.

## Managed tasks and output pages

Tasks keeps an explicit project workspace independent of Jobs and Storage.
Choose a readable project by its authorized name. Project choices are bounded
pages; More projects reads the next page and selecting a project applies it.
Moving the highlight does not change the current scope. Scripts can discover
the same labels and exact keys with `sai runs workspaces --site site-a`.
The explicit `--tasks-workspace-key` option remains available without creating
a fake project choice. Every task read rechecks current access.

The task list includes accepted managed runs that have left the live queue.
Enter opens the recorded status and its source time. It does not query Slurm or
turn an uncertain submission into success. In a narrow window the selected
task's evidence uses the main area; Escape rereads the preceding list page and
restores the selected row. File pages remain explicitly loaded and bounded.

Stdout, Stderr and Files are explicit reads under the task's current file
permissions. They replace a single bounded page; Next follows the returned
cursor and Start returns to the first page. Logs and file pages do not auto-poll,
and changing the project clears earlier protected data. A denied directory does
not hide still-authorized task metadata. Output filenames describe current files
under the declared roots, not a sealed result version. Pilot's native document
preview remains the file viewer; this terminal slice does not create one.

After loading a task's details, Open Web (W or the command palette) opens that
exact managed run in the console's read-only task page. The link contains only
the applied project, site and run reference; it uses the configured Portal
origin. The browser authenticates and authorizes the read again, including
separate file permission checks. It can open a historical run without reading
the first list page, an active scheduler account or a Pilot runtime.
The shared visible link and Copy link action also work over SSH without a local
desktop browser. Refreshing, changing project or losing task access clears the
link; typing in a text input never triggers W. Neither navigation nor copying
starts a computation, changes the default identity or extends a runtime window.

## Continue in the console

After a successful job detail or allocation read, Open Web asks Portal to
resolve that exact observed job to its current authorized workspace. It does
not infer a project from an account name or the Overview's default identity.
The same reader handles this request; changing context discards a late link.
Known submission/restart changes ask for a fresh terminal snapshot first.

The fixed same-origin console link opens that job directly, including array
task zero and jobs outside the first list page. The browser authenticates again
and reads a complete current allocation. Older observation evidence is retained
only for an explicit changed/unknown notice, never as permanent execution ID.
If self job read is still allowed but the destination workspace is denied, the
terminal keeps the original observation and shows the navigation refusal.

Keyboard actions share the visible controls: A opens allocation, W prepares
the Web link, and Ctrl+P lists available actions through Textual's native command
palette. Text inputs and selectors retain their own keys. The three compact
controls remain visible at 40 columns. A short clickable link and explicit Copy
link action work when an SSH host has no desktop browser; copying uses the
terminal's clipboard support and never runs automatically.

## Interaction references

The [terminal design rules](../DESIGN.md) specify context, language, selection,
information hierarchy and visual verification. The CLI defaults to Chinese;
`--language en-US` selects English. Protocol keys and user-provided names are
unchanged. Local visual checks do not establish real SSH or long-session
acceptance, and the broader workbench is still being developed.

Reviewed on 2026-09-23:

- [Codex footer source](https://github.com/openai/codex/blob/b7add4df3d95e2d41249e54d3c3a1bd14680848a/codex-rs/tui/src/bottom_pane/footer.rs)
  adjusts hints to available width and editing/running context.
- [Claude Code interactive-mode documentation](https://code.claude.com/docs/en/interactive-mode)
  distinguishes editing, dialog and running-task keyboard behavior. This is
  documentation evidence, not a claim to have inspected its implementation.
- [OpenCode keybindings](https://opencode.ai/docs/keybinds/) document command
  discovery and explicit key combinations that avoid editing conflicts.

SAI reuses these interaction principles through existing Textual controls and
actions. It does not introduce another Agent loop, permission system or command
framework. Wider task/result navigation and hardware correlation remain separate.

## Validation and remaining work

Headless tests exercise the real HTTP client through resource comparison,
partition selection, detail/allocation requests and independently denied estimates.
Allocation tests use separate local Portal and gateway HTTP origins, array tasks
including zero, snapshot replacement, denied reads and missing configuration.
Delayed-result tests exercise scope replacement, old permission failures and
request coalescing, including job/mode/tab changes during allocation reads.
Nullable/duplicate estimate identities use snapshot-local
UI rows, not invented business identifiers. Small-window checks cover the
layout and accessible control positions; local synthetic screenshots are not
real infrastructure acceptance.

The full [unified workbench](unified-workbench.md) still needs direct Pilot result
navigation, richer resource eligibility and hardware telemetry. Managed task
history, logs and output listings now reuse the existing Run/readback contracts;
job context can continue into the console's existing Pilot handoff.
Native storage quota is implemented locally;
site installation, service-UID permissions and real Lustre behavior still require
acceptance. The privileged storage write adapter is not used by this UI or
packaged with the read gateway. Keep 3D after truthful data.
