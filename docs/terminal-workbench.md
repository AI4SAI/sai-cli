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

1. Resources is the site's published catalog. It has no account, job state or
   partition filters. Press Enter to select a compute candidate and read its
   title, summary, use cases, hardware, QOS and published price. Press C or
   Compare to add or remove that candidate from a comparison of at most two
   resources. Candidate selection and comparison remain separate. Narrow
   terminals show compared resources in sequence; wide terminals use columns.
   Unknown facts remain unknown. Published capacity is not idle capacity, and
   neither admission nor a concrete job quote is established here.
2. Prepare in Pilot (W) opens the same-origin console resource preparation page
   with only the site and selected partition reference. The browser chooses the
   project and checks authority and a concrete plan. This works before a user
   has any job history and makes no extra CLI API request. Storage offerings
   cannot be selected as compute partitions. Refresh, errors and tab changes
   clear the candidate and Web link; inspecting a candidate pauses catalog
   polling. Copy link remains explicit for terminals without a local browser.
3. Use View jobs to apply the explicitly selected candidate partition to the Jobs
   view. Change scope, account name/ID, partition or states and select Apply.
   The applied context remains visible; draft controls do not change authority.
4. Press Enter on a job or choose Details for its separately authorized
   detail. Allocation instead requests one allocation snapshot from the
   explicitly configured site gateway. Escape returns to the list. Ordinary
   detail uses native site-read mode when configured and the existing Portal
   transport otherwise. Allocation requires native configuration and capability
   mode; missing configuration displays an error. Neither path falls back.
5. Open Running estimates to request the independent billing DTO. Enter shows
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

After an allocation read, Recorded location explicitly requests the independent
`jobs.placement` operation. `sai jobs placement JOB_ID` exposes the same bounded
read outside the TUI. The site must opt in to publishing approved operator
registrations; allocation permission alone does not grant location access.
The response includes the complete allocation used for its node association,
plus inventory revision, validity and each node's recorded, unmapped or expired
registration. A successful read replaces allocation and registration together.
Operator-supplied asset/incarnation references and rack U positions do not prove
that the current machine still matches that registration.

Location inspection does not poll. Refresh removes old registrations before
reading again; a source failure leaves the independent allocation readable but
does not restore old locations. Permission loss clears protected results.
Registration validity has its own deadline cleanup, independent of the polling
interval, and expiration sends no additional request. This is a local consumer
implementation; it does not establish a published inventory or deployed gateway.

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

- F5 or Refresh requests an update. F6 pauses/resumes automatic refresh only
  where automatic reads are supported;
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

All six views share three layouts: browse for lists and project discovery,
inspect for a selected object, and summary for Overview and Storage. Inspection
keeps the current object above the evidence. At 40 or 60 columns, or below 28
rows, the list and filters give way to the evidence; at 100 columns with enough
height, a compact list stays available. Escape affects only the current view.
For Resources it returns to the catalog without another read and preserves the
separate comparison choices.

Layout does not decide freshness. Ordinary job and managed-task details retain
automatic reads. Resource inspection, selected estimates, allocation/location
snapshots, project discovery and task logs/files remain manual. Those modes
offer Refresh without Pause/Resume; F6 cannot discard a selected output or imply
that polling has resumed. Footer, visible controls and command palette use the
same contextual actions, with short footer labels and searchable command titles,
through Textual's public interfaces.
Empty estimates explain that no estimate is available. Failed reads keep a
bounded explanation and retry action visible after protected data is cleared.

## Managed tasks and output pages

Cost is an explicit mode of the selected task, with its own current billing
permission. It presents one final-cost observation and does not poll. Standard
usage, cash, Credit equivalent/points, reserved coverage and price adjustment
come from Portal's shared validator and formatter. Hidden funding components
are omitted; pending/unavailable/non-chargeable responses carry no invented
amounts. A cost-only denial leaves task metadata readable, while Run-scope
revocation and authentication failure keep the existing protected-data cleanup.
W opens the exact Run's Cost tab without putting amounts in the URL.

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

Files uses a keyboard-selectable list. Full relative paths wrap without
shortening; byte size and modification time remain separate. Arrow keys browse,
and Enter confirms the highlighted file with a visible Selected file marker.
Ctrl+Up/Down scrolls within long entries without changing the selected file.
Selection makes no request. Moving to another file clears the confirmation;
changing the project, run, page or evidence mode clears selection and any link.

After loading a task's details, Open Web (W or the command palette) opens that
exact managed run in the console's read-only task page. With a confirmed file,
it additionally selects Files and carries that file's existing `artifact_ref`
and the current page's request cursor. The initial cursor is omitted when the
request omitted it; `next_cursor` is never used for the current selection.
Paths, sizes, contents and credentials never enter the URL. Without a confirmed
file, the existing run-only link remains available. Links use the configured
Portal origin. The browser authenticates and authorizes the read again, including
separate file permission checks. It can open a historical run without reading
the first list page, an active scheduler account or a Pilot runtime.
The browser reads the referenced page and finds the file by reference. If the
page changed and the file is absent, it asks for a refresh instead of selecting
another file. The terminal does not read file contents, create a Pilot session
or send an Agent message.

## Continue a recorded result in Pilot

Files can also be carried into the existing SAI Pilot flow. The console link
keeps only the exact run reference, selected artifact reference and the request
cursor for the bounded page. The console rechecks the run, current file READ
permission and the selected page before showing the original Session. It never
places a path or file content in the URL. The user confirms the original
Session, and only then resumes it or explicitly renews its existing window.

Pilot receives a same-tab reference containing the run and optional
artifact. It rechecks the selected native Session and current file before
opening the native file viewer or inserting an editable evidence prompt. It
does not submit a message automatically. A missing file, changed page, lost
permission, mismatched Session or stale response leaves the task reference
visible and gives the user a refresh or return action.

This continuation reuses the existing Portal Run readback and Pilot native file
viewer. It does not create a result archive, new task engine, second file
browser, implicit runtime start or hidden renewal. Agent `run.get`, `run.logs`
and `artifact.list` use the same current project READ owner as the console;
submission, cancellation and confirmation retain their separate execution
authority.

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
unchanged. Bilingual navigation, paginated project discovery, confirmation
separate from highlight, narrow-window task details and return-to-list selection
are implemented. The shared layout applies the existing teal theme, evidence
hierarchy and contextual actions across all six views. Local rendered review
covers both languages and narrow/short windows. A bounded real SSH run now
covers task evidence, resizing, colour/monochrome modes and disconnect cleanup.
Physical terminal fonts, clipboard behaviour, network diversity and longer
production sessions still require comprehensive acceptance.

Reviewed on 2026-09-23:

- [Codex footer source](https://github.com/openai/codex/blob/b7add4df3d95e2d41249e54d3c3a1bd14680848a/codex-rs/tui/src/bottom_pane/footer.rs)
  adjusts hints to available width and editing/running context.
- [Claude Code interactive-mode documentation](https://code.claude.com/docs/en/interactive-mode)
  distinguishes editing, dialog and running-task keyboard behavior. This is
  documentation evidence, not a claim to have inspected its implementation.
- [OpenCode keybindings](https://opencode.ai/docs/keybinds/) document command
  discovery and explicit key combinations that avoid editing conflicts.
- [Textual selection source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_option_list.py)
  distinguishes highlighted options from explicit selection; its native
  controls and command palette are the implementation building blocks here.

These references inform specific interactions: contextual footer hints,
editing-safe keys, discoverable actions and explicit object selection. They do
not establish reuse of Codex, Claude Code or OpenCode application source or their
Agent systems. SAI implements the interactions with Textual and its existing
read client. These references do not establish complete product acceptance.

## Validation and remaining work

Tasks can explicitly read node registrations through Location. The action uses
the existing allocation/placement evidence panel and shared expiry timer; the
six task-mode controls stay compact. Full paths and source evidence remain
scrollable at 40 columns. Registration expiry discards locations and keeps only
that response's allocation; it cannot restore old statistics or a different Run.
The Web continuation remains on the Run page, with a current server binding on
every location read. Ordinary job navigation retains its separate purpose.

Statistics is an explicit task mode, alongside history, logs, files and cost.
It uses the same scoped reader and a separate manual observation. The six mode
buttons stay visible as a 3×2 grid below 60 columns and one row otherwise. Step
CPU/RSS facts precede provenance in short windows; null metrics stay unknown,
CPU time never gets a percent sign, and the query window is not native sample
time. This keeps the existing teal theme, bilingual labels and keyboard rules.

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

A local Linux PTY check uses real terminal input and window-size signals at
100×32, 60×18 and 40×24. Resizing remains responsive during a deliberately delayed
local HTTP read; Ctrl+Q restores terminal modes and exits the alternate screen.
This does not verify a remote SSH connection, emulator/font diversity,
reconnection or a long-running production session.

The later [SSH acceptance](ssh-terminal-acceptance.md) used a formal runtime on
one login host with synthetic HTTP facts. A 14-minute Chinese run and separate
English checks passed real VT interaction, three sizes, expiry/denial recovery,
in-flight resize, normal terminal restoration and disconnect cleanup. It did
not switch the shared entrypoint or validate production authentication. RSS
growth and the remaining terminal/font/long-duration boundaries are recorded
there rather than hidden behind an overall product-readiness claim.

Registered-location checks cover scope binding, exact node correspondence,
unknown/expired records and independent failure cleanup. The Web consumer uses
the same contract in the existing allocation dialog and may mark only disclosed
U segments on generic node models. It does not show a whole cabinet's occupancy
or infer that undisplayed positions are empty. Synthetic inventory and local
HTTP/browser tests do not verify a current physical machine or location.

The full [unified workbench](unified-workbench.md) still needs richer resource
eligibility, estimate-to-final replacement and hardware telemetry. Explicit
Run cost now uses verified final-fact association and independent financial
visibility; this is not deployed billing acceptance. Managed task history,
logs and output listings reuse the existing Run/readback contracts; selected
outputs can continue through the console into their original Pilot Session.
Local continuation checks do not establish deployed or real-site acceptance.
Native storage quota is implemented locally;
site installation, service-UID permissions and real Lustre behavior still require
acceptance. The privileged storage write adapter is not used by this UI or
packaged with the read gateway. Keep 3D after truthful data.
